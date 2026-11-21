#!/usr/bin/env python3
"""Stage GNU Gzip with deterministic, translation-friendly normalization."""

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


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if text.count(old) != 1:
        raise RuntimeError(f"GNU Gzip {label} precondition failed in {path}")
    path.write_text(text.replace(old, new))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    canonical = repository / "work/upstream/gzip-1.14"
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["gzip"]
    state = json.loads((repository / "work/upstream/.state/gzip.json").read_text())
    for key in (
        "version", "sha256", "signature_sha256", "signer_fingerprint", "key_sha256"
    ):
        if state.get(key) != release[key]:
            raise RuntimeError(f"GNU Gzip source state changed at {key}")
    if not state["signature_verified"]:
        raise RuntimeError("canonical GNU Gzip release signature is not verified")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    try:
        shutil.copytree(canonical, staged, symlinks=True)

        entry = staged / "gzip.c"
        replace_once(
            entry,
            "int main (int argc, char **argv)\n{",
            "int rustbox_gzip_main (int argc, char **argv);\n\n"
            "int\n"
            "rustbox_gzip_main (int argc, char **argv)\n{",
            "multicall entrypoint",
        )
        entry.write_text(entry.read_text() + (
            "\n#ifndef RUSTBOX_MULTICALL\n"
            "int\n"
            "main (int argc, char **argv)\n"
            "{\n"
            "  return rustbox_gzip_main (argc, argv);\n"
            "}\n"
            "#endif\n"
        ))
        replace_once(
            entry,
            "    do_exit(exit_code);\n}",
            "    do_exit(exit_code);\n"
            "    return exit_code;\n"
            "}",
            "explicit nonreturning main tail",
        )

        replace_once(
            staged / "deflate.c",
            '    if (pack_level < 1 || pack_level > 9) gzip_error ("bad pack level");',
            '    if (pack_level < 1 || pack_level > 9)\n'
            '      {\n'
            '        gzip_error ("bad pack level");\n'
            '        return;\n'
            '      }',
            "explicit fatal pack-level boundary",
        )

        replace_once(
            staged / "lib/vasnprintf.c",
            "      r_ptr = roomptr;\n"
            "      r_len = a_len;\n"
            "      memcpy (r_ptr, a_ptr, a_len * sizeof (mp_limb_t));",
            "      r_ptr = roomptr;\n"
            "      r_len = a_len;\n"
            "      if (a_len != 0)\n"
            "        memcpy (r_ptr, a_ptr, a_len * sizeof (mp_limb_t));",
            "zero-length null memcpy guard",
        )
        replace_once(
            staged / "lib/malloca.c",
            "  idx_t nplus;\n"
            "  if (!ckd_add (&nplus, n, plus) && !xalloc_oversized (nplus, 1))",
            "  idx_t nplus;\n"
            "  if (n <= (size_t) (IDX_MAX - plus)\n"
            "      && (nplus = (idx_t) n + plus, !xalloc_oversized (nplus, 1)))",
            "explicit checked malloc size width",
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
            raise RuntimeError("normalization added or removed GNU Gzip source-tree files")
        changed = sorted(
            name for name in canonical_files
            if sha256(canonical / name) != sha256(staged / name)
        )
        expected = ["deflate.c", "gzip.c", "lib/malloca.c", "lib/vasnprintf.c"]
        if changed != expected:
            raise RuntimeError(f"unexpected GNU Gzip normalized sources: {changed}")

        operations = {
            "deflate.c": (
                "make the nonreturning invalid pack-level path explicit before the configuration-table index"
            ),
            "gzip.c": (
                "export rustbox_gzip_main, retain a conditional standalone main wrapper, and make the unreachable return after do_exit explicit to translation tools"
            ),
            "lib/vasnprintf.c": (
                "do not pass a possibly null source to memcpy when the multi-precision copy length is zero"
            ),
            "lib/malloca.c": (
                "replace the generic checked-add expression with the equivalent explicit idx_t range check and assignment"
            ),
        }
        manifest = {
            "schema": 1,
            "release": release["version"],
            "canonical_archive_sha256": release["sha256"],
            "canonical_tree_sha256": tree_digest(canonical),
            "normalized_tree_sha256": tree_digest(staged),
            "changed_sources": changed,
            "conditional": "RUSTBOX_MULTICALL",
            "compiler_normalization": (
                "gl_cv_crc_pclmul=no selects GNU Gzip's canonical portable CRC path for C2Rust"
            ),
            "engine": "exact deterministic source rewrite",
            "transformations": [
                {
                    "source": name,
                    "canonical_sha256": sha256(canonical / name),
                    "normalized_sha256": sha256(staged / name),
                    "operation": operations[name],
                }
                for name in changed
            ],
        }
        if output.exists():
            shutil.rmtree(output)
        staged.rename(output)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"changed_sources": changed, "entrypoints": 1}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
