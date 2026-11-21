#!/usr/bin/env python3
"""Stage GNU Grep with deterministic translator-oriented C normalization."""

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


def replace_exact(path: Path, replacements: list[tuple[str, str, int]]) -> None:
    text = path.read_text()
    for before, after, expected in replacements:
        if text.count(before) != expected:
            raise RuntimeError(
                f"normalization precondition failed in {path}: "
                f"expected {expected} occurrences of {before!r}, found {text.count(before)}"
            )
        text = text.replace(before, after)
    path.write_text(text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    canonical = repository / "work/upstream/grep-3.12"
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["grep"]
    state = json.loads((repository / "work/upstream/.state/grep.json").read_text())
    for key in ("version", "sha256", "signature_sha256", "signer_fingerprint", "key_sha256"):
        if state.get(key) != release[key]:
            raise RuntimeError(f"GNU Grep source state changed at {key}")
    if not state["signature_verified"]:
        raise RuntimeError("canonical GNU Grep release signature is not verified")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    try:
        shutil.copytree(canonical, staged, symlinks=True)

        entry = staged / "src/grep.c"
        before = entry.read_text()
        signature = "int\nmain (int argc, char **argv)\n{"
        replacement = (
            "int rustbox_grep_main (int argc, char **argv);\n\n"
            "int\n"
            "rustbox_grep_main (int argc, char **argv)\n{"
        )
        if before.count(signature) != 1 or "rustbox_grep_main" in before:
            raise RuntimeError("GNU Grep entrypoint normalization precondition failed")
        wrapper = (
            "\n#ifndef RUSTBOX_MULTICALL\n"
            "int\n"
            "main (int argc, char **argv)\n"
            "{\n"
            "  return rustbox_grep_main (argc, argv);\n"
            "}\n"
            "#endif\n"
        )
        entry.write_text(before.replace(signature, replacement) + wrapper)

        replace_exact(entry, [
            ("ckd_add (&sum, a, b)", "ckd_add (&sum, a, (intmax_t) b)", 1),
            ("ckd_add (&a, to_be_read, save + min_after_buflim)",
             "ckd_add (&a, (ptrdiff_t) to_be_read,\n"
             "                            (ptrdiff_t) (save + min_after_buflim))", 1),
            ("command_line &= ent->fts_level == FTS_ROOTLEVEL;",
             "command_line = ent->fts_level == FTS_ROOTLEVEL && command_line;", 1),
            ("status &= grepdirent (fts, ent, command_line);",
             "status = grepdirent (fts, ent, command_line) && status;", 1),
            ("status &= grep_command_line_arg (*files++);",
             "status = grep_command_line_arg (*files++) && status;", 1),
            ("out_invert ^= true;", "out_invert = !out_invert;", 1),
        ])
        replace_exact(staged / "src/dfasearch.c", [
            ("dc->begline |= dm->begline;",
             "dc->begline = dm->begline || dc->begline;", 1),
            ("pat.fastmap = syntax_only | match_icase ? nullptr : ximalloc (uchar_max + 1);",
             "pat.fastmap = (syntax_only | match_icase)\n"
             "                ? nullptr : ximalloc (uchar_max + 1);", 1),
        ])
        replace_exact(staged / "src/pcresearch.c", [
            ("ckd_mul (&lim, lim, 2)", "ckd_mul (&lim, lim, (uint32_t) 2)", 1),
        ])
        replace_exact(staged / "src/kwset.c", [
            ("ckd_mul (&len12, len, 12)", "ckd_mul (&len12, len, (idx_t) 12)", 1),
        ])
        replace_exact(staged / "lib/malloca.c", [
            ("  idx_t nplus;\n  if (!ckd_add (&nplus, n, plus) && !xalloc_oversized (nplus, 1))",
             "  idx_t nplus;\n  if (n <= (size_t) (IDX_MAX - plus)\n"
             "      && (nplus = (idx_t) n + plus, !xalloc_oversized (nplus, 1)))", 1),
        ])
        replace_exact(staged / "lib/xstrtol.c", [
            ("ckd_mul (&scaled, *x, scale_factor)",
             "ckd_mul (&scaled, *x, (__strtol_t) scale_factor)", 1),
        ])
        replace_exact(staged / "lib/realloc.c", [
            ("  ptrdiff_t signed_n;\n  if (ckd_add (&signed_n, n, 0))\n"
             "    {\n      errno = ENOMEM;\n      return NULL;\n    }",
             "  if (PTRDIFF_MAX < n)\n"
             "    {\n      errno = ENOMEM;\n      return NULL;\n    }", 1),
        ])
        replace_exact(staged / "lib/dfa.c", [
            ("stk[-2].nullable &= stk[-1].nullable;",
             "stk[-2].nullable = stk[-1].nullable && stk[-2].nullable;", 1),
            ("stk[-2].nullable |= stk[-1].nullable;",
             "stk[-2].nullable = stk[-1].nullable || stk[-2].nullable;", 1),
            ("mergeit &= d->multibyte_prop[group.elems[j].index];",
             "mergeit = (d->multibyte_prop[group.elems[j].index]\n"
             "                           && mergeit);", 1),
            ("lmp->begline &= rmp->begline;",
             "lmp->begline = rmp->begline && lmp->begline;", 1),
            ("lmp->endline &= rmp->endline;",
             "lmp->endline = rmp->endline && lmp->endline;", 1),
        ])
        replace_exact(staged / "lib/strstr.c", [
            ("ok &= *haystack++ == *needle++;",
             "ok = *haystack++ == *needle++ && ok;", 1),
        ])

        canonical_files = {
            path.relative_to(canonical).as_posix()
            for path in canonical.rglob("*") if path.is_file()
        }
        staged_files = {
            path.relative_to(staged).as_posix()
            for path in staged.rglob("*") if path.is_file()
        }
        if canonical_files != staged_files:
            raise RuntimeError("normalization added or removed GNU Grep source-tree files")
        changed = sorted(
            name for name in canonical_files
            if sha256(canonical / name) != sha256(staged / name)
        )
        expected_changed = [
            "lib/dfa.c", "lib/malloca.c", "lib/realloc.c", "lib/strstr.c",
            "lib/xstrtol.c", "src/dfasearch.c", "src/grep.c", "src/kwset.c",
            "src/pcresearch.c",
        ]
        if changed != expected_changed:
            raise RuntimeError(f"unexpected GNU Grep normalized sources: {changed}")

        transformations = []
        for name in changed:
            transformations.append({
                "source": name,
                "canonical_sha256": sha256(canonical / name),
                "normalized_sha256": sha256(staged / name),
                "operation": (
                    "export the multicall entrypoint and make eager Boolean accumulation explicit"
                    if name == "src/grep.c" else
                    "parenthesize audited precedence and make Boolean accumulation explicit"
                    if name == "src/dfasearch.c" else
                    "make checked-integer widths or Boolean accumulation explicit for C2Rust"
                ),
                "engine": "exact deterministic translator-compatibility rewrite",
            })
        manifest = {
            "schema": 1,
            "release": release["version"],
            "canonical_archive_sha256": release["sha256"],
            "canonical_tree_sha256": tree_digest(canonical),
            "normalized_tree_sha256": tree_digest(staged),
            "changed_sources": changed,
            "transformations": transformations,
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
    print(json.dumps({"changed_sources": 9, "entrypoints": 1}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
