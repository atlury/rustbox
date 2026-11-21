#!/usr/bin/env python3
"""Summarize deterministic GNU Grep normalization and parity gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summaries(path: Path) -> list[dict[str, int]]:
    blocks = re.findall(
        r"# TOTAL:\s+(\d+).*?# PASS:\s+(\d+).*?# SKIP:\s+(\d+)"
        r".*?# XFAIL:\s+(\d+).*?# FAIL:\s+(\d+).*?# XPASS:\s+(\d+)"
        r".*?# ERROR:\s+(\d+)", path.read_text(errors="replace"), re.DOTALL,
    )
    return [dict(zip(
        ("total", "pass", "skip", "xfail", "fail", "xpass", "error"), map(int, block)
    )) for block in blocks]


def production_sources(database: Path, compiler: str) -> tuple[list[str], int, int]:
    records = json.loads(database.read_text())
    prefix = "/rustbox-grep/normalized-source/"
    sources: set[str] = set()
    tests = 0
    for record in records:
        source = str(record["file"])
        if source.startswith(prefix + "gnulib-tests/"):
            tests += 1
        elif source.startswith(prefix + "lib/") or source.startswith(prefix + "src/"):
            sources.add(source.removeprefix(prefix))
        elif source == f"/rustbox-grep/normalized-{compiler}/lib/colorize.c":
            sources.add("generated/lib/colorize.c")
        else:
            raise RuntimeError(f"unexpected normalized Grep source {source}")
    return sorted(sources), len(records), tests


def needed(path: Path) -> list[str]:
    output = subprocess.run(
        ["readelf", "-d", str(path)], check=True, text=True, stdout=subprocess.PIPE
    ).stdout
    return re.findall(r"Shared library: \[([^]]+)\]", output)


def global_symbols(path: Path) -> dict[str, str]:
    output = subprocess.run(
        ["nm", "-g", str(path)], check=True, text=True, stdout=subprocess.PIPE
    ).stdout
    symbols: dict[str, str] = {}
    for line in output.splitlines():
        fields = line.split()
        if len(fields) == 3:
            symbols[fields[2]] = fields[1]
    return symbols


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    base = repository / "work/analysis/grep-3.12/normalized"
    oracle = json.loads((repository / "evidence/grep-3.12-oracle.json").read_text())
    manifest_path = base / "normalization.json"
    manifest = json.loads(manifest_path.read_text())
    if len(manifest["changed_sources"]) != 9 or "src/grep.c" not in manifest["changed_sources"]:
        raise RuntimeError("GNU Grep normalization manifest changed")

    expected = {
        "gcc": [oracle["tests"]["gcc"]["grep"], oracle["tests"]["gcc"]["gnulib"]],
        "clang": [oracle["tests"]["clang"]["grep"], oracle["tests"]["clang"]["gnulib"]],
        "sanitizer": [oracle["tests"]["sanitizer"]["grep"], oracle["tests"]["sanitizer"]["gnulib"]],
    }
    actual = {compiler: summaries(base / f"{compiler}-check.log") for compiler in expected}
    if actual != expected:
        raise RuntimeError(f"normalized GNU Grep suite totals changed: {actual}")

    source_sets: dict[str, list[str]] = {}
    actions: dict[str, int] = {}
    test_actions: dict[str, int] = {}
    database_hashes: dict[str, str] = {}
    for compiler in ("gcc", "clang", "sanitizer"):
        database = base / f"{compiler}-compile-commands.json"
        sources, count, tests = production_sources(database, compiler)
        source_sets[compiler] = sources
        actions[compiler] = count
        test_actions[compiler] = tests
        database_hashes[compiler] = sha256(database)
    if any(sources != source_sets["gcc"] for sources in source_sets.values()):
        raise RuntimeError("normalized GNU Grep compiler source closures differ")
    if source_sets["gcc"] != oracle["scope"]["production_sources"]:
        raise RuntimeError("normalized GNU Grep closure differs from canonical oracle")

    differentials = {}
    for compiler in ("gcc", "clang"):
        path = base / f"canonical-normalized-{compiler}-differential.json"
        report = json.loads(path.read_text())
        if report["comparisons"] != 36 or not report["gcc_clang_exact"]:
            raise RuntimeError(f"GNU Grep normalized {compiler} differential changed")
        differentials[compiler] = {
            "comparisons": report["comparisons"],
            "exact": True,
            "sha256": sha256(path),
        }

    valgrind_text = (base / "valgrind.log").read_text(errors="replace")
    for expected_line in (
        "definitely lost: 0 bytes in 0 blocks",
        "indirectly lost: 0 bytes in 0 blocks",
        "possibly lost: 18,688 bytes in 11 blocks",
        "still reachable: 119,466 bytes in 39 blocks",
        "ERROR SUMMARY: 3 errors",
    ):
        if expected_line not in valgrind_text:
            raise RuntimeError(f"normalized GNU Grep Valgrind baseline changed: {expected_line}")

    binaries = {}
    objects = {}
    for compiler in ("gcc", "clang"):
        binary = base / f"grep-{compiler}"
        dependencies = needed(binary)
        if dependencies != oracle["configuration"]["oracle_dynamic_dependencies"]:
            raise RuntimeError(f"normalized GNU Grep dependencies changed: {dependencies}")
        symbols = global_symbols(base / f"grep-{compiler}.o")
        if symbols.get("rustbox_grep_main") not in ("T", "t") or symbols.get("main") not in ("T", "t"):
            raise RuntimeError(f"normalized GNU Grep entrypoint symbols changed: {compiler}")
        binaries[compiler] = {
            "bytes": binary.stat().st_size,
            "sha256": sha256(binary),
            "needed": dependencies,
        }
        objects[compiler] = {
            "sha256": sha256(base / f"grep-{compiler}.o"),
            "entrypoints": ["main", "rustbox_grep_main"],
        }

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-21",
        "release": "3.12",
        "normalization": manifest,
        "scope": {
            "production_sources": len(source_sets["gcc"]),
            "captured_compile_actions": actions,
            "test_support_compile_actions": test_actions,
            "source_closure_matches_canonical": True,
            "compile_database_sha256": database_hashes,
        },
        "tests": {
            compiler: {
                "grep": totals[0], "gnulib": totals[1],
                "log_sha256": sha256(base / f"{compiler}-check.log"),
            }
            for compiler, totals in actual.items()
        },
        "canonical_normalized_differential": {
            "comparisons": 72,
            "exact": True,
            "compilers": differentials,
        },
        "valgrind": {
            "matches_canonical_summary": True,
            "log_sha256": sha256(base / "valgrind.log"),
        },
        "binaries": binaries,
        "entrypoint_objects": objects,
        "next_gate": "translate the exact 129-source normalized production closure with C2Rust",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"changed_sources": 9, "differential": 72, "production_sources": 129}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
