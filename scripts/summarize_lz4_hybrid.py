#!/usr/bin/env python3
"""Publish canonical-parity and size evidence for translated LZ4."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def section(path: Path, name: str) -> int:
    match = re.search(rf"^{re.escape(name)}\s+(\d+)\s+", path.read_text(), re.MULTILINE)
    if not match:
        raise RuntimeError(f"missing {name} in {path}")
    return int(match.group(1))


def needed(path: Path) -> list[str]:
    return re.findall(r"Shared library: \[([^]]+)\]", path.read_text())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/lz4-1.11.1/hybrid"
    build = repository / "build/lz4-1.11.1-hybrid"

    differential_path = analysis / "differential.json"
    differential = json.loads(differential_path.read_text())
    if differential.get("cases") != 27 or differential.get("passed") != 27:
        raise RuntimeError("translated LZ4 differential suite is incomplete")
    upstream_path = analysis / "upstream-tests.log"
    upstream_text = upstream_path.read_text(errors="replace")
    markers = [
        "test lz4 basic compression/decompression", "test command line options",
        "test --list", "test lz4 multithreaded compression",
        "make: Leaving directory",
    ]
    if "make: ***" in upstream_text or any(marker not in upstream_text for marker in markers):
        raise RuntimeError("translated LZ4 upstream essentials suite is incomplete")

    expected_heaps = {
        "compress": {
            "canonical": "total heap usage: 9 allocs, 9 frees, 8,410,567 bytes allocated",
            "hybrid": "total heap usage: 9 allocs, 9 frees, 8,410,567 bytes allocated",
        },
        "decompress": {
            "canonical": "total heap usage: 29 allocs, 29 frees, 29,633,156 bytes allocated",
            "hybrid": "total heap usage: 29 allocs, 29 frees, 29,633,220 bytes allocated",
        },
    }
    valgrind = {}
    for operation, summaries in expected_heaps.items():
        logs = {}
        heaps = {}
        for implementation, expected in summaries.items():
            log = analysis / f"valgrind-{operation}-{implementation}.log"
            text = log.read_text(errors="replace")
            if (
                "ERROR SUMMARY: 0 errors" not in text
                or "All heap blocks were freed -- no leaks are possible" not in text
                or expected not in text
            ):
                raise RuntimeError(
                    f"LZ4 {operation} {implementation} Valgrind baseline changed"
                )
            logs[implementation] = sha256(log)
            heaps[implementation] = expected
        valgrind[operation] = {
            "errors": 0,
            "all_allocations_freed": True,
            "heap_summary": heaps,
            "log_sha256": logs,
            "translation_overhead": (
                "none" if operation == "compress" else
                "one fully freed 64-byte Rust process-startup allocation"
            ),
        }

    binary = build / "lz4"
    stripped = build / "lz4.stripped"
    canonical = build / "lz4.canonical-stripped"
    expected_needed = ["libm.so.6", "libgcc_s.so.1", "libc.so.6", "ld-linux-x86-64.so.2"]
    dynamic = build / "lz4.dynamic"
    if needed(dynamic) != expected_needed:
        raise RuntimeError(f"unexpected LZ4 dependencies: {needed(dynamic)!r}")
    sections_path = build / "lz4.sections"

    translation = json.loads((repository / "evidence/lz4-1.11.1-c2rust.json").read_text())
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-21",
        "release": "1.11.1",
        "status": "complete translated hybrid at canonical parity; all four names integrated into Rustbox",
        "implementation": {
            "rust_production_sources": 12,
            "rust_files": translation["stable_translation"]["rust_files"],
            "public_names": ["lz4", "lz4c", "lz4cat", "unlz4"],
            "entrypoints": ["rustbox_lz4_main"],
            "generated_rust_semantic_repairs": 0,
            "c_abi_glue": "entrypoint only",
            "embedded_liblz4_and_xxhash": True,
        },
        "behavior": {
            "upstream_essentials": "pass",
            "upstream_markers": markers,
            "upstream_log_sha256": sha256(upstream_path),
            "differential": differential,
            "differential_sha256": sha256(differential_path),
            "valgrind": valgrind,
        },
        "size": {
            "translation_static_archive_bytes": translation["stable_translation"]["archive"]["bytes"],
            "linked_unstripped_bytes": binary.stat().st_size,
            "linked_stripped_bytes": stripped.stat().st_size,
            "canonical_stripped_bytes": canonical.stat().st_size,
            "linked_sha256": sha256(binary),
            "stripped_sha256": sha256(stripped),
            "sections": {
                name.removeprefix("."): section(sections_path, name)
                for name in (".text", ".rodata", ".data", ".bss")
            },
            "dynamic_needed": expected_needed,
            "interpretation": "The static archive is link inventory, not release size; Rust runtime code is shared after multicall integration.",
        },
        "configuration": {
            "external_liblz4": False, "f128": False,
            "selinux": False, "systemd": False,
        },
        "input_evidence": {
            name: sha256(repository / f"evidence/{name}")
            for name in (
                "lz4-1.11.1-oracle.json", "lz4-1.11.1-analysis.json",
                "lz4-1.11.1-normalization.json", "lz4-1.11.1-c2rust.json",
            )
        },
        "next_gate": "complete; unified dispatch evidence is in evidence/rustbox-multicall.json",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "differential": differential["passed"],
        "stripped_bytes": stripped.stat().st_size,
        "upstream": "pass",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
