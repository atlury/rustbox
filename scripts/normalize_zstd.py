#!/usr/bin/env python3
"""Stage zstd with a deterministic translation-friendly entrypoint."""

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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    canonical = repository / "work/upstream/zstd-1.5.7"
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["zstd"]
    state = json.loads((repository / "work/upstream/.state/zstd.json").read_text())
    for key in ("version", "sha256", "checksum_sha256", "commit", "tag"):
        if state.get(key) != release[key]:
            raise RuntimeError(f"zstd source state changed at {key}")
    if not state["checksum_verified"] or not state["integrity_verified"]:
        raise RuntimeError("canonical zstd checksum state is incomplete")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    changed: list[str] = []
    try:
        shutil.copytree(canonical, staged, symlinks=True)
        entry = staged / "programs/zstdcli.c"
        text = entry.read_text()
        old = "int main(int argCount, const char* argv[])\n{"
        new = "int rustbox_zstd_main(int argCount, const char* argv[])\n{"
        if text.count(old) != 1:
            raise RuntimeError("zstd entrypoint precondition failed")
        text = text.replace(old, new)
        text += (
            "\n#ifndef RUSTBOX_MULTICALL\n"
            "int main(int argc, const char* argv[])\n"
            "{\n"
            "    return rustbox_zstd_main(argc, argv);\n"
            "}\n"
            "#endif\n"
        )
        entry.write_text(text)

        canonical_files = {path.relative_to(canonical).as_posix()
                           for path in canonical.rglob("*") if path.is_file()}
        staged_files = {path.relative_to(staged).as_posix()
                        for path in staged.rglob("*") if path.is_file()}
        if canonical_files != staged_files:
            raise RuntimeError("normalization added or removed zstd source-tree files")
        changed = sorted(name for name in canonical_files
                         if sha256(canonical / name) != sha256(staged / name))
        if changed != ["programs/zstdcli.c"]:
            raise RuntimeError(f"unexpected zstd normalized sources: {changed}")

        manifest = {
            "schema": 1, "release": release["version"],
            "canonical_archive_sha256": release["sha256"],
            "canonical_tree_sha256": tree_digest(canonical),
            "normalized_tree_sha256": tree_digest(staged),
            "changed_sources": changed, "entrypoints": 1,
            "conditional": "RUSTBOX_MULTICALL",
            "compiler_normalization": "ZSTD_NO_ASM=1 selects upstream portable C Huffman decoding and excludes the optional x86-64 assembly unit",
            "engine": "exact deterministic source rewrite",
            "transformations": [{
                "source": "programs/zstdcli.c",
                "canonical_sha256": sha256(canonical / "programs/zstdcli.c"),
                "normalized_sha256": sha256(entry),
                "operation": "export rustbox_zstd_main and retain a conditional standalone main wrapper",
            }],
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
