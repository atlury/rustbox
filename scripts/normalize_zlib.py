#!/usr/bin/env python3
"""Stage an exact, transactional zlib source tree for translation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
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
        patch_records = []
        patch_plan = (
            ("uncompr.c", "normalization/zlib/split-z-size-declarators.cocci"),
            ("compress.c", "normalization/zlib/explicit-z-size.cocci"),
            ("uncompr.c", "normalization/zlib/explicit-z-size.cocci"),
        )
        for name, patch_name in patch_plan:
            target = staged_source / name
            before = target.read_bytes()
            transformed = target.with_name(target.name + ".spatch-output.c")
            semantic_patch = repository / patch_name
            process = subprocess.run(
                ["spatch", "--sp-file", str(semantic_patch), str(target), "-o", str(transformed)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if process.returncode or not transformed.is_file():
                raise RuntimeError(f"Coccinelle failed for {name}: {process.stderr[-4000:]}")
            transformed.replace(target)
            patch_records.append({
                "source": name,
                "semantic_patch": patch_name,
                "before_sha256": hashlib.sha256(before).hexdigest(),
                "after_sha256": sha256(target),
            })
        if (staged_source / "compress.c").read_text().count(
            "z_size_t got = (z_size_t)*destLen;"
        ) != 1:
            raise RuntimeError("compress.c explicit-size postcondition failed")
        uncompr = (staged_source / "uncompr.c").read_text()
        if uncompr.count("z_size_t got = (z_size_t)*destLen") != 1 or uncompr.count(
            "used = (z_size_t)*sourceLen"
        ) != 1:
            raise RuntimeError("uncompr.c explicit-size postcondition failed")
        normalized_digest = tree_digest(staged_source)

        source_records = {
            name: {
                "canonical_sha256": sha256(source / name),
                "normalized_sha256": sha256(staged_source / name),
                "changed": sha256(source / name) != sha256(staged_source / name),
            }
            for name in production
        }
        manifest = {
            "schema": 1,
            "release": release["version"],
            "canonical_archive_sha256": release["sha256"],
            "canonical_tree_sha256": canonical_digest,
            "normalized_tree_sha256": normalized_digest,
            "strategy": "Coccinelle declarator split and explicit target-width conversions",
            "transformations": patch_records,
            "reason": (
                "C2Rust preserves C unsigned long and size_t as distinct Rust u64 and "
                "usize types. Three canonical implicit conversions are made explicit; "
                "both types are 64-bit in the declared x86_64 target ABI."
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

    print(json.dumps({"changed_sources": 2, "production_sources": 15}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
