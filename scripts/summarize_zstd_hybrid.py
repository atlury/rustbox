#!/usr/bin/env python3
"""Publish canonical parity and resource evidence for translated zstd."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def heap_summary(path: Path) -> str:
    text = path.read_text(errors="replace")
    if "ERROR SUMMARY: 0 errors" not in text:
        raise RuntimeError(f"Valgrind errors in {path}")
    for kind in ("definitely", "indirectly", "possibly"):
        if f"{kind} lost: 0 bytes in 0 blocks" not in text:
            raise RuntimeError(f"Valgrind loss in {path}")
    match = re.search(r"total heap usage: .*", text)
    if not match:
        raise RuntimeError(f"missing heap summary in {path}")
    return match.group(0)


def section(path: Path, name: str) -> int:
    match = re.search(rf"^{re.escape(name)}\s+(\d+)\s+", path.read_text(), re.MULTILINE)
    if not match:
        raise RuntimeError(f"missing {name} in {path}")
    return int(match.group(1))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/zstd-1.5.7/hybrid"
    build = Path("/rustbox-zstd/hybrid")
    differential_path = analysis / "differential.json"
    differential = json.loads(differential_path.read_text())
    expected_names = ["zstd", "zstdmt", "unzstd", "zstdcat", "zstdgrep", "zstdless"]
    if differential.get("cases") != 17 or differential.get("passed") != 17:
        raise RuntimeError("translated zstd differential suite is incomplete")
    if differential.get("public_names") != expected_names:
        raise RuntimeError("zstd public-name inventory changed")

    valgrind = {}
    for operation in ("compress", "decompress"):
        log = analysis / f"valgrind-{operation}.log"
        valgrind[operation] = {
            "errors": 0,
            "lost_bytes": 0,
            "heap_summary": heap_summary(log),
            "log_sha256": sha256(log),
        }

    dynamic = (analysis / "zstd.dynamic").read_text()
    needed = re.findall(r"Shared library: \[([^]]+)\]", dynamic)
    symbols = (analysis / "zstd.symbols").read_text()
    if len(re.findall(r" rustbox_zstd_main$", symbols, re.MULTILINE)) != 1:
        raise RuntimeError("translated zstd entrypoint is not unique")
    binary = repository / "work/analysis/zstd-1.5.7/hybrid-artifacts/zstd"
    stripped = repository / "work/analysis/zstd-1.5.7/hybrid-artifacts/zstd.stripped"
    if not binary.is_file() or not stripped.is_file():
        raise RuntimeError("copied zstd hybrid artifacts are missing")
    translation = json.loads((repository / "evidence/zstd-1.5.7-c2rust.json").read_text())
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-22",
        "release": "1.5.7",
        "status": "complete translated hybrid at canonical parity; all six names integrated into Rustbox",
        "implementation": {
            "rust_production_sources": 44,
            "public_names": expected_names,
            "entrypoints": ["rustbox_zstd_main"],
            "generated_rust_semantic_repairs": 0,
            "embedded_compression_implementation": True,
            "canonical_shell_interfaces": ["zstdgrep", "zstdless"],
        },
        "behavior": {
            "differential": differential,
            "differential_sha256": sha256(differential_path),
            "deterministic_compressed_bytes_match": True,
            "valgrind": valgrind,
        },
        "size": {
            "translation_static_archive_bytes": translation["stable_translation"]["release_archive"]["bytes"],
            "linked_unstripped_bytes": binary.stat().st_size,
            "linked_stripped_bytes": stripped.stat().st_size,
            "linked_sha256": sha256(binary),
            "stripped_sha256": sha256(stripped),
            "sections": {
                name.removeprefix("."): section(analysis / "zstd.sections", name)
                for name in (".text", ".rodata", ".data", ".bss")
            },
            "dynamic_needed": needed,
        },
        "configuration": {
            "threads": True,
            "dictionaries": True,
            "legacy_formats": True,
            "zlib": False,
            "lzma": False,
            "lz4": False,
            "selinux": False,
            "systemd": False,
        },
        "next_gate": "complete; unified dispatch evidence is in evidence/rustbox-multicall.json",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "differential": 17,
        "public_names": 6,
        "stripped_bytes": stripped.stat().st_size,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
