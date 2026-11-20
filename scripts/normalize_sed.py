#!/usr/bin/env python3
"""Stage GNU sed with deterministic translator-oriented C normalization."""

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
                f"expected {expected} occurrences of {before!r}"
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
    canonical = repository / "work/upstream/sed-4.10"
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["sed"]
    state = json.loads((repository / "work/upstream/.state/sed.json").read_text())
    for key in ("version", "sha256", "signature_sha256", "signer_fingerprint", "key_sha256"):
        if state.get(key) != release[key]:
            raise RuntimeError(f"GNU sed source state changed at {key}")
    if not state["signature_verified"]:
        raise RuntimeError("canonical GNU sed release signature is not verified")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    try:
        shutil.copytree(canonical, staged, symlinks=True)

        entry = staged / "sed/sed.c"
        before = entry.read_text()
        signature = "int\nmain (int argc, char **argv)\n{"
        replacement = (
            "int rustbox_sed_main (int argc, char **argv);\n\n"
            "int\nrustbox_sed_main (int argc, char **argv)\n{"
        )
        if before.count(signature) != 1 or "rustbox_sed_main" in before:
            raise RuntimeError("GNU sed entrypoint normalization precondition failed")
        wrapper = (
            "\n#ifndef RUSTBOX_MULTICALL\n"
            "int\nmain (int argc, char **argv)\n"
            "{\n"
            "  return rustbox_sed_main (argc, argv);\n"
            "}\n"
            "#endif\n"
        )
        entry.write_text(before.replace(signature, replacement) + wrapper)

        replace_exact(staged / "sed/regexp.c", [
            ("  regoff_t buflen_regoff;\n  if (ckd_add (&buflen_regoff, buflen, 0))\n    panic (_(\"regex input buffer length overflow\"));",
             "  if (INTMAX_MAX < buflen)\n    panic (_(\"regex input buffer length overflow\"));\n  regoff_t buflen_regoff = (regoff_t) buflen;", 1),
        ])
        replace_exact(staged / "sed/compile.c", [
            ("ckd_mul (&num, num, 10)", "ckd_mul (&num, num, (intmax_t) 10)", 1),
            ("ckd_add (&num, num, ch - '0')",
             "ckd_add (&num, num, (intmax_t) (ch - '0'))", 1),
        ])
        replace_exact(staged / "sed/execute.c", [
            ("ckd_mul (&backup_size, asterisks, name_length - 1)",
             "ckd_mul (&backup_size, (ptrdiff_t) asterisks, name_length - 1)", 1),
            ("ckd_add (&backup_size, backup_size, strlen (in_place_extension) + 1)",
             "ckd_add (&backup_size, backup_size,\n                  (ptrdiff_t) strlen (in_place_extension) + 1)", 1),
        ])
        replace_exact(staged / "lib/malloca.c", [
            ("  idx_t nplus;\n  if (!ckd_add (&nplus, n, plus) && !xalloc_oversized (nplus, 1))",
             "  idx_t nplus;\n  if (n <= (size_t) (IDX_MAX - plus)\n      && (nplus = (idx_t) n + plus, !xalloc_oversized (nplus, 1)))", 1),
        ])
        replace_exact(staged / "lib/realloc.c", [
            ("  ptrdiff_t signed_n;\n  if (ckd_add (&signed_n, n, 0))\n    {\n      errno = ENOMEM;\n      return NULL;\n    }",
             "  if (PTRDIFF_MAX < n)\n    {\n      errno = ENOMEM;\n      return NULL;\n    }", 1),
        ])
        replace_exact(staged / "lib/obstack.c", [
            ("  v |= ckd_add (&s, obj_size, length);",
             "  v = ckd_add (&s, obj_size, length) || v;", 1),
            ("  v |= align_chunk_size_up (&s, h->alignment_mask, s);",
             "  v = align_chunk_size_up (&s, h->alignment_mask, s) || v;", 1),
            ("  v |= ckd_add (&s, s,\n                (offsetof (struct _obstack_chunk, contents)\n                 + h->alignment_mask));",
             "  v = ckd_add (&s, s,\n               (offsetof (struct _obstack_chunk, contents)\n                + h->alignment_mask)) || v;", 1),
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
            raise RuntimeError("normalization added or removed GNU sed source-tree files")
        changed = sorted(
            name for name in canonical_files
            if sha256(canonical / name) != sha256(staged / name)
        )
        expected_changed = [
            "lib/malloca.c", "lib/obstack.c", "lib/realloc.c",
            "sed/compile.c", "sed/execute.c", "sed/regexp.c", "sed/sed.c",
        ]
        if changed != expected_changed:
            raise RuntimeError(f"unexpected GNU sed normalized sources: {changed}")

        transformations = []
        for name in changed:
            transformations.append({
                "source": name,
                "canonical_sha256": sha256(canonical / name),
                "normalized_sha256": sha256(staged / name),
                "operation": (
                    "export the multicall entrypoint" if name == "sed/sed.c" else
                    "make checked-integer widths and eager Boolean accumulation explicit for C2Rust"
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
    print(json.dumps({"changed_sources": 7, "entrypoints": 1}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

