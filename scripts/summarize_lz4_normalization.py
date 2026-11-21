#!/usr/bin/env python3
"""Publish deterministic LZ4 normalization and parity evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def needed(path: Path) -> list[str]:
    output = subprocess.run(
        ["readelf", "-d", str(path)], check=True, text=True, stdout=subprocess.PIPE
    ).stdout
    return re.findall(r"Shared library: \[([^]]+)\]", output)


def symbols(path: Path) -> set[str]:
    output = subprocess.run(
        ["nm", "-g", "--defined-only", str(path)], check=True, text=True,
        stdout=subprocess.PIPE,
    ).stdout
    return {line.split()[-1] for line in output.splitlines() if len(line.split()) >= 3}


def heap_summary(path: Path) -> str:
    text = path.read_text(errors="replace")
    match = re.search(
        r"total heap usage: [0-9,]+ allocs, [0-9,]+ frees, [0-9,]+ bytes allocated",
        text,
    )
    for phrase in (
        "All heap blocks were freed -- no leaks are possible",
        "ERROR SUMMARY: 0 errors",
    ):
        if phrase not in text:
            raise RuntimeError(f"incomplete Valgrind result in {path}")
    if not match:
        raise RuntimeError(f"missing Valgrind heap line in {path}")
    return match.group(0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    base = repository / "work/analysis/lz4-1.11.1/normalized"
    oracle_dir = repository / "work/analysis/lz4-1.11.1/oracle"
    oracle = json.loads((repository / "evidence/lz4-1.11.1-oracle.json").read_text())
    manifest_path = base / "normalization.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest["changed_sources"] != ["lib/lz4frame.c", "programs/lz4cli.c"]:
        raise RuntimeError("LZ4 normalization source set changed")

    expected_sources = oracle["inventory"]["production_sources"]
    check_markers = [
        "test lz4 basic compression/decompression", "test command line options",
        "test --list", "test lz4 multithreaded compression",
    ]
    compilers = {}
    source_sets = []
    for compiler in ("gcc", "clang", "sanitizer"):
        database = base / f"{compiler}-compile-commands.json"
        commands = json.loads(database.read_text())
        prefix = f"/rustbox-lz4/normalized-{compiler}/"
        sources = sorted({record["file"].removeprefix(prefix) for record in commands})
        if (
            len(commands) != 24 or len(sources) != 12
            or any(not record["file"].startswith(prefix) for record in commands)
        ):
            raise RuntimeError(f"normalized LZ4 {compiler} compilation closure changed")
        source_sets.append(sources)
        log = base / f"{compiler}-check.log"
        text = log.read_text(errors="replace")
        if (
            "make: ***" in text or any(marker not in text for marker in check_markers)
            or (compiler == "sanitizer" and (
                "ERROR: AddressSanitizer" in text
                or re.search(r"\.c:\d+(?::\d+)?: runtime error:", text)
            ))
        ):
            raise RuntimeError(f"normalized LZ4 {compiler} suite is incomplete")
        compilers[compiler] = {
            "compile_actions": len(commands),
            "production_sources": len(sources),
            "compile_database_sha256": sha256(database),
            "upstream_essentials_log_sha256": sha256(log),
            "passed": True,
        }
    if any(sources != source_sets[0] for sources in source_sets[1:]):
        raise RuntimeError("normalized LZ4 compiler source closures differ")
    if source_sets[0] != expected_sources:
        raise RuntimeError("normalized LZ4 closure differs from canonical oracle")

    differentials = {}
    for compiler in ("gcc", "clang"):
        path = base / f"canonical-normalized-{compiler}-differential.json"
        report = json.loads(path.read_text())
        if report.get("cases") != 27 or report.get("passed") != 27:
            raise RuntimeError(f"normalized LZ4 {compiler} differential changed")
        differentials[compiler] = {
            "comparisons": 27, "exact": True, "sha256": sha256(path),
        }

    binaries = {}
    for compiler in ("gcc", "clang"):
        binary = base / compiler / "lz4"
        defined = symbols(binary)
        if not {"main", "rustbox_lz4_main"}.issubset(defined):
            raise RuntimeError(f"normalized LZ4 {compiler} entrypoints changed")
        libraries = needed(binary)
        if libraries != ["libc.so.6"]:
            raise RuntimeError(f"normalized LZ4 dependency set changed: {libraries}")
        with tempfile.TemporaryDirectory(prefix="rustbox-lz4-normalized-strip-") as temporary:
            stripped = Path(temporary) / "lz4"
            shutil.copy2(binary, stripped)
            subprocess.run(["strip", "--strip-all", str(stripped)], check=True)
            stripped_bytes = stripped.stat().st_size
            stripped_sha256 = sha256(stripped)
        binaries[compiler] = {
            "bytes": binary.stat().st_size,
            "sha256": sha256(binary),
            "stripped_bytes": stripped_bytes,
            "stripped_sha256": stripped_sha256,
            "needed": libraries,
            "entrypoints": ["main", "rustbox_lz4_main"],
            "embedded_liblz4_and_xxhash": True,
        }

    resources = {}
    for operation in ("compress", "decompress"):
        normalized_path = base / f"valgrind-{operation}.log"
        normalized_summary = heap_summary(normalized_path)
        canonical_summary = heap_summary(oracle_dir / f"valgrind-{operation}.log")
        if normalized_summary != canonical_summary:
            raise RuntimeError(f"normalized LZ4 {operation} resource summary differs")
        resources[operation] = {
            "matches_canonical_summary": True,
            "heap_summary": normalized_summary,
            "log_sha256": sha256(normalized_path),
        }

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-21",
        "release": "1.11.1",
        "normalization": manifest,
        "scope": {
            "production_sources": 12,
            "source_closure_matches_canonical": True,
            "compilers": compilers,
        },
        "canonical_normalized_differential": {
            "comparisons": 54, "exact": True, "compilers": differentials,
        },
        "resources": resources,
        "binaries": binaries,
        "manifest_sha256": sha256(manifest_path),
        "configuration": {
            "external_liblz4": False,
            "force_memory_access": 0,
            "multithreaded": True,
            "selinux": False,
            "systemd": False,
        },
        "next_gate": "translate the exact 12-source normalized LZ4 production closure with C2Rust",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "changed_sources": 2, "differential": 54, "production_sources": 12,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
