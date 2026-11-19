#!/usr/bin/env python3
"""Stage an exact, transactional zlib source tree for translation."""

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
            kind = b"L"
            payload = os.readlink(path).encode()
        elif path.is_file():
            kind = b"F"
            payload = path.read_bytes()
        elif path.is_dir():
            kind = b"D"
            payload = b""
        else:
            raise RuntimeError(f"unsupported source entry: {path}")
        digest.update(kind + b"\0" + relative + b"\0" + payload + b"\0")
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    source = repository / "work/upstream/zlib-1.4"
    state = json.loads((repository / "work/upstream/.state/zlib.json").read_text())
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["zlib"]
    if not state["signature_verified"] or state["sha256"] != release["sha256"]:
        raise RuntimeError("canonical zlib source is not signature-verified")

    production = sorted(path.name for path in source.glob("*.c"))
    if len(production) != 15:
        raise RuntimeError(f"expected 15 production C files, found {len(production)}")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    published = temporary / output.name
    staged_source = published / "source"
    try:
        shutil.copytree(source, staged_source, symlinks=True)
        canonical_digest = tree_digest(source)
        normalized_digest = tree_digest(staged_source)
        if canonical_digest != normalized_digest:
            raise RuntimeError("zero-change normalization altered the source tree")

        source_records = {
            name: {
                "canonical_sha256": sha256(source / name),
                "normalized_sha256": sha256(staged_source / name),
                "changed": False,
            }
            for name in production
        }
        manifest = {
            "schema": 1,
            "release": release["version"],
            "canonical_archive_sha256": release["sha256"],
            "canonical_tree_sha256": canonical_digest,
            "normalized_tree_sha256": normalized_digest,
            "strategy": "exact-source zero-change normalization",
            "transformations": [],
            "reason": (
                "The exact canonical C already compiles under GCC and Clang, passes "
                "the upstream, sanitizer, and Valgrind gates, and has no demonstrated "
                "translator failure that would justify a semantic rewrite."
            ),
            "production_sources": source_records,
        }
        (published / "normalization.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        if output.exists():
            shutil.rmtree(output)
        published.rename(output)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)

    print(json.dumps({"changed_sources": 0, "production_sources": 15}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
