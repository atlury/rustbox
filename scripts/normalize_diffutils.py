#!/usr/bin/env python3
"""Stage GNU Diffutils with deterministic multicall entrypoint normalization."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix().encode()
        if path.is_symlink():
            kind, payload = b"L", os.readlink(path).encode()
        elif path.is_file():
            kind, payload = b"F", path.read_bytes()
        elif path.is_dir():
            kind, payload = b"D", b""
        else:
            raise RuntimeError(f"unsupported source entry: {path}")
        digest.update(kind + b"\0" + relative + b"\0" + payload + b"\0")
    return digest.hexdigest()


def normalize_entrypoint(path: Path, name: str, signature: str) -> None:
    before = path.read_text()
    export = f"rustbox_{name}_main"
    if before.count(signature) != 1 or export in before:
        raise RuntimeError(f"GNU Diffutils {name} entrypoint precondition failed")
    arguments = "char *argv[]" if name == "sdiff" else "char **argv"
    replacement = (
        f"int {export} (int argc, {arguments});\n\n"
        "int\n"
        f"{export} (int argc, {arguments})\n"
        "{"
    )
    wrapper = (
        "\n#ifndef RUSTBOX_MULTICALL\n"
        "int\n"
        f"main (int argc, {arguments})\n"
        "{\n"
        f"  return {export} (argc, argv);\n"
        "}\n"
        "#endif\n"
    )
    path.write_text(before.replace(signature, replacement) + wrapper)
    if path.read_text().count(export) != 3:
        raise RuntimeError(f"GNU Diffutils {name} entrypoint postcondition failed")


def replace_exact(path: Path, before: str, after: str, expected: int = 1) -> None:
    text = path.read_text()
    if text.count(before) != expected:
        raise RuntimeError(
            f"GNU Diffutils normalization precondition failed for {path}: "
            f"expected {expected} matches, found {text.count(before)}"
        )
    path.write_text(text.replace(before, after))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    canonical = repository / "work/upstream/diffutils-3.12"
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["diffutils"]
    state = json.loads((repository / "work/upstream/.state/diffutils.json").read_text())
    for key in ("version", "sha256", "signature_sha256", "signer_fingerprint", "key_sha256"):
        if state.get(key) != release[key]:
            raise RuntimeError(f"GNU Diffutils source state changed at {key}")
    if not state["signature_verified"]:
        raise RuntimeError("canonical GNU Diffutils release signature is not verified")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    try:
        shutil.copytree(canonical, staged, symlinks=True)
        normalize_entrypoint(staged / "src/cmp.c", "cmp", "int\nmain (int argc, char **argv)\n{")
        normalize_entrypoint(staged / "src/diff.c", "diff", "int\nmain (int argc, char **argv)\n{")
        normalize_entrypoint(staged / "src/diff3.c", "diff3", "int\nmain (int argc, char **argv)\n{")
        normalize_entrypoint(staged / "src/sdiff.c", "sdiff", "int\nmain (int argc, char *argv[])\n{")

        # Make non-returning control flow explicit for C2Rust.  This is after
        # a _Noreturn call and is unreachable in the canonical program.
        replace_exact(
            staged / "lib/c-stack.c",
            "  die (SIGSEGV);\n}",
            "  die (SIGSEGV);\n  __builtin_unreachable ();\n}",
        )

        # C23 checked arithmetic converts both operands to a common type and
        # then converts to the destination type.  C2Rust 0.22 instead chooses
        # Rust's overflowing_* receiver type from the first operand.  Spell
        # the already-equivalent x86_64 Linux destination types explicitly so
        # every generated overflowing operation has one exact Rust type.
        replace_exact(
            staged / "lib/malloca.c",
            "if (!ckd_add (&nplus, n, plus) && !xalloc_oversized (nplus, 1))",
            "if (n <= IDX_MAX\n"
            "      && !ckd_add (&nplus, (idx_t) n, (idx_t) plus)\n"
            "      && !xalloc_oversized (nplus, 1))",
        )
        replace_exact(
            staged / "lib/mktime.c",
            "ckd_sub (&negative_offset_guess, 0, off)",
            "ckd_sub (&negative_offset_guess, 0, (int) off)",
        )
        replace_exact(
            staged / "lib/mktime.c",
            "ckd_add (&ot, t, delta * direction)",
            "ckd_add (&ot, t, (long_int) (delta * direction))",
        )
        replace_exact(
            staged / "lib/mktime.c",
            "ckd_sub (offset, *offset, negative_offset_guess)",
            "ckd_sub (offset, *offset, (mktime_offset_t) negative_offset_guess)",
        )
        replace_exact(
            staged / "lib/xstrtol.c",
            "ckd_mul (&scaled, *x, scale_factor)",
            "ckd_mul (&scaled, *x, (__strtol_t) scale_factor)",
        )
        replace_exact(
            staged / "src/analyze.c",
            "ckd_add (&blksize[f], ST_BLKSIZE (cmp->file[f].stat), 0)",
            "ckd_add (&blksize[f], (idx_t) ST_BLKSIZE (cmp->file[f].stat), (idx_t) 0)",
        )
        replace_exact(
            staged / "src/cmp.c",
            "ckd_add (&blksize[f], ST_BLKSIZE (stat_buf[0]), 0)",
            "ckd_add (&blksize[f], (idx_t) ST_BLKSIZE (stat_buf[0]), (idx_t) 0)",
        )
        replace_exact(
            staged / "src/context.c",
            "ckd_mul (&non_ignorable_threshold, context, 2)",
            "ckd_mul (&non_ignorable_threshold, context, (lin) 2)",
        )
        replace_exact(
            staged / "src/diff.c",
            "if (ckd_add (&size, size, optsize))",
            "if (IDX_MAX < optsize || ckd_add (&size, size, (idx_t) optsize))",
        )
        replace_exact(
            staged / "src/diff.c",
            "ckd_mul (&ocontext, ocontext, 10)",
            "ckd_mul (&ocontext, ocontext, (lin) 10)",
        )
        replace_exact(
            staged / "src/diff.c",
            "ckd_add (&ocontext, ocontext, c - '0')",
            "ckd_add (&ocontext, ocontext, (lin) (c - '0'))",
        )
        replace_exact(
            staged / "src/diff3.c",
            "ckd_add (&current_chunk_size, ST_BLKSIZE (pipestat), 0)",
            "ckd_add (&current_chunk_size, (idx_t) ST_BLKSIZE (pipestat), (idx_t) 0)",
        )
        replace_exact(
            staged / "src/io.c",
            "ckd_add (&blksize, ST_BLKSIZE (current->stat), 0)",
            "ckd_add (&blksize, (idx_t) ST_BLKSIZE (current->stat), (idx_t) 0)",
        )
        replace_exact(
            staged / "src/io.c",
            "ckd_add (&cc, file_size - file_size % sizeof (word), extra_room)",
            "ckd_add (&cc, (idx_t) (file_size - file_size % sizeof (word)),\n"
            "                    (idx_t) extra_room)",
        )
        replace_exact(
            staged / "src/io.c",
            "ckd_add (&current->bufsize, current->buffered, extra_room)",
            "ckd_add (&current->bufsize, current->buffered, (idx_t) extra_room)",
        )
        replace_exact(
            staged / "src/side.c",
            "ckd_add (&in_position, in_position, width)",
            "ckd_add (&in_position, in_position, (intmax_t) width)",
        )
        replace_exact(
            staged / "src/side.c",
            "ckd_add (&in_position, in_position, 1)",
            "ckd_add (&in_position, in_position, (intmax_t) 1)",
        )

        # Assign Boolean results through logical operators.  Operands have no
        # side effects except the named call, which remains unconditionally
        # evaluated by placing it first where necessary.
        replace_exact(
            staged / "src/diff3.c",
            "show_2nd |= !incompat & merge;",
            "show_2nd = show_2nd || (!incompat && merge);",
        )
        replace_exact(
            staged / "src/diff3.c",
            "flagging |= !incompat & merge;",
            "flagging = flagging || (!incompat && merge);",
        )
        replace_exact(
            staged / "src/diff3.c",
            "leading_dot |= dotlines (outputfile, b, mapping[FILE2]);",
            "leading_dot = dotlines (outputfile, b, mapping[FILE2]) || leading_dot;",
        )
        replace_exact(
            staged / "src/io.c",
            "appears_binary |= sip (&filevec[1], skip_test | appears_binary);",
            "appears_binary = sip (&filevec[1], skip_test | appears_binary)\n"
            "                   || appears_binary;",
        )
        replace_exact(
            staged / "src/side.c",
            "put_newline |= left[1][-1] == '\\n';",
            "put_newline = left[1][-1] == '\\n' || put_newline;",
        )
        replace_exact(
            staged / "src/side.c",
            "put_newline |= right[1][-1] == '\\n';",
            "put_newline = right[1][-1] == '\\n' || put_newline;",
        )

        canonical_files = {
            path.relative_to(canonical).as_posix()
            for path in canonical.rglob("*") if path.is_file()
        }
        staged_files = {
            path.relative_to(staged).as_posix()
            for path in staged.rglob("*") if path.is_file()
        }
        if canonical_files != staged_files:
            raise RuntimeError("normalization added or removed GNU Diffutils source-tree files")
        changed = sorted(
            name for name in canonical_files
            if sha256(canonical / name) != sha256(staged / name)
        )
        expected_changed = [
            "lib/c-stack.c",
            "lib/malloca.c",
            "lib/mktime.c",
            "lib/xstrtol.c",
            "src/analyze.c",
            "src/cmp.c",
            "src/context.c",
            "src/diff.c",
            "src/diff3.c",
            "src/io.c",
            "src/sdiff.c",
            "src/side.c",
        ]
        if changed != expected_changed:
            raise RuntimeError(f"unexpected GNU Diffutils normalized sources: {changed}")

        transformations = [
            {
                "source": name,
                "canonical_sha256": sha256(canonical / name),
                "normalized_sha256": sha256(staged / name),
                "operation": (
                    f"export rustbox_{Path(name).stem}_main with a conditional standalone main wrapper"
                    + (
                        "; also make checked arithmetic or Boolean assignment explicit for C2Rust"
                        if name in {"src/cmp.c", "src/diff.c", "src/diff3.c"}
                        else ""
                    )
                    if name in {"src/cmp.c", "src/diff.c", "src/diff3.c", "src/sdiff.c"}
                    else "make checked arithmetic, Boolean assignment, or non-returning control flow explicit for C2Rust"
                ),
                "engine": "exact deterministic source rewrite",
            }
            for name in changed
        ]
        manifest = {
            "schema": 1,
            "release": release["version"],
            "canonical_archive_sha256": release["sha256"],
            "canonical_tree_sha256": tree_digest(canonical),
            "normalized_tree_sha256": tree_digest(staged),
            "changed_sources": changed,
            "transformations": transformations,
            "entrypoints": ["rustbox_cmp_main", "rustbox_diff_main", "rustbox_diff3_main", "rustbox_sdiff_main"],
            "conditional": "RUSTBOX_MULTICALL",
            "engine": "exact deterministic source rewrite",
        }
        if output.exists():
            shutil.rmtree(output)
        staged.rename(output)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"changed_sources": 12, "entrypoints": 4}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
