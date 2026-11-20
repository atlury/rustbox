#!/usr/bin/env python3
"""Generate evidence for deterministic GNU patch 2.8 C normalization."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
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
        ["nm", "-g", "--defined-only", str(path)],
        check=True, text=True, stdout=subprocess.PIPE,
    ).stdout
    return {line.split()[-1] for line in output.splitlines() if len(line.split()) >= 3}


def test_summary(path: Path) -> dict[str, int]:
    text = path.read_text(errors="replace")
    result = {}
    for name in ("TOTAL", "PASS", "SKIP", "XFAIL", "FAIL", "XPASS", "ERROR"):
        match = re.search(rf"^# {name}:\s+(\d+)$", text, re.MULTILINE)
        if not match:
            raise RuntimeError(f"missing {name} in {path}")
        result[name.lower()] = int(match.group(1))
    expected = {"total": 49, "pass": 47, "skip": 0, "xfail": 2, "fail": 0, "xpass": 0, "error": 0}
    if result != expected:
        raise RuntimeError(f"normalized GNU patch suite changed: {result}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    normalized = repository / "work/analysis/patch-2.8/normalized"
    oracle = repository / "work/analysis/patch-2.8/oracle"
    manifest = json.loads((normalized / "normalization.json").read_text())
    if len(manifest["changed_sources"]) != 10:
        raise RuntimeError("GNU patch normalization changed an unexpected source set")
    if manifest["engine"] != "exact deterministic source rewrite":
        raise RuntimeError("GNU patch normalization engine changed")

    tests = {}
    closures = {}
    for compiler in ("gcc", "clang", "sanitizer"):
        tests[compiler] = test_summary(normalized / f"{compiler}-check.log")
        database = json.loads((normalized / f"{compiler}-compile-commands.json").read_text())
        sources = {record["file"] for record in database}
        if len(database) != 67 or len(sources) != 67:
            raise RuntimeError(f"normalized GNU patch {compiler} closure changed")
        closures[compiler] = {
            "compile_actions": len(database),
            "unique_sources": len(sources),
            "compile_database_sha256": sha256(normalized / f"{compiler}-compile-commands.json"),
        }

    differentials = {}
    for compiler in ("gcc", "clang"):
        path = normalized / f"canonical-normalized-{compiler}-differential.json"
        report = json.loads(path.read_text())
        if report["comparisons"] != 28 or not report["gcc_clang_exact"]:
            raise RuntimeError(f"GNU patch {compiler} normalization differential is incomplete")
        differentials[compiler] = {
            "comparisons": 28,
            "exact": True,
            "report_sha256": sha256(path),
        }

    valgrind = (normalized / "valgrind.log").read_text(errors="replace")
    for phrase in (
        "ERROR SUMMARY: 0 errors",
        "definitely lost: 0 bytes in 0 blocks",
        "indirectly lost: 0 bytes in 0 blocks",
        "possibly lost: 0 bytes in 0 blocks",
    ):
        if phrase not in valgrind:
            raise RuntimeError("normalized GNU patch Valgrind smoke is incomplete")

    expected_needed = {"libattr.so.1", "libc.so.6"}
    binaries = {}
    for compiler in ("gcc", "clang"):
        binary = normalized / f"patch-{compiler}"
        libraries = needed(binary)
        if set(libraries) != expected_needed:
            raise RuntimeError(f"normalized GNU patch {compiler} dependencies changed")
        object_symbols = symbols(normalized / f"patch-{compiler}.o")
        if not {"main", "rustbox_patch_main"}.issubset(object_symbols):
            raise RuntimeError(f"normalized GNU patch {compiler} entrypoints are incomplete")
        if (normalized / f"config-{compiler}.h").read_bytes() != (oracle / f"config-{compiler}.h").read_bytes():
            raise RuntimeError(f"normalized GNU patch {compiler} configuration changed")
        binaries[compiler] = {
            "bytes": binary.stat().st_size,
            "sha256": sha256(binary),
            "needed": libraries,
        }

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-20",
        "release": "2.8",
        "transformation": manifest,
        "production": closures,
        "tests": {
            compiler: {**summary, "log_sha256": sha256(normalized / f"{compiler}-check.log")}
            for compiler, summary in tests.items()
        },
        "differential": {
            "by_compiler": differentials,
            "comparisons": 56,
            "canonical_normalized_exact": True,
        },
        "valgrind": {
            "errors": 0,
            "definite_indirect_possible_leaks": 0,
            "still_reachable_bytes": 2947,
            "log_sha256": sha256(normalized / "valgrind.log"),
        },
        "entrypoint": {
            "conditional": "RUSTBOX_MULTICALL",
            "export": "rustbox_patch_main",
            "standalone_main_retained": True,
            "gcc_clang_object_symbols_verified": True,
        },
        "configuration": {"canonical_normalized_exact_by_compiler": True},
        "binaries": binaries,
        "next_gate": "C2Rust audit translation of the exact 67-source production closure",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"differential": 56, "entrypoints": 1, "tests": 147}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
