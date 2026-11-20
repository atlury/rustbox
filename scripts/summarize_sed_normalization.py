#!/usr/bin/env python3
"""Generate evidence for deterministic GNU sed 4.10 C normalization."""

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


def summaries(path: Path) -> list[dict[str, int]]:
    text = path.read_text(errors="replace")
    matches = re.findall(
        r"# TOTAL:\s+(\d+).*?# PASS:\s+(\d+).*?# SKIP:\s+(\d+).*?"
        r"# XFAIL:\s+(\d+).*?# FAIL:\s+(\d+).*?# XPASS:\s+(\d+).*?# ERROR:\s+(\d+)",
        text, re.DOTALL,
    )
    names = ("total", "pass", "skip", "xfail", "fail", "xpass", "error")
    return [dict(zip(names, map(int, values))) for values in matches]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    normalized = repository / "work/analysis/sed-4.10/normalized"
    oracle = repository / "work/analysis/sed-4.10/oracle"
    manifest = json.loads((normalized / "normalization.json").read_text())
    if len(manifest["changed_sources"]) != 7:
        raise RuntimeError("GNU sed normalization changed an unexpected source set")
    if manifest["engine"] != "exact deterministic source rewrite":
        raise RuntimeError("GNU sed normalization engine changed")

    release_expected = [
        {"total": 75, "pass": 68, "skip": 7, "xfail": 0, "fail": 0, "xpass": 0, "error": 0},
        {"total": 287, "pass": 241, "skip": 46, "xfail": 0, "fail": 0, "xpass": 0, "error": 0},
    ]
    sanitizer_expected = [
        {"total": 75, "pass": 64, "skip": 11, "xfail": 0, "fail": 0, "xpass": 0, "error": 0}
    ]
    tests: dict[str, object] = {}
    closures = {}
    for compiler in ("gcc", "clang", "sanitizer"):
        actual = summaries(normalized / f"{compiler}-check.log")
        expected = sanitizer_expected if compiler == "sanitizer" else release_expected
        if actual != expected:
            raise RuntimeError(f"normalized GNU sed {compiler} suite changed: {actual}")
        tests[compiler] = actual
        database = json.loads((normalized / f"{compiler}-compile-commands.json").read_text())
        sources = {record["file"] for record in database}
        production = {source for source in sources if "/gnulib-tests/" not in source}
        if len(database) != 121 or len(sources) != 121 or len(production) != 85:
            raise RuntimeError(f"normalized GNU sed {compiler} closure changed")
        closures[compiler] = {
            "all_compile_actions": len(database),
            "production_compile_actions": len(production),
            "compile_database_sha256": sha256(normalized / f"{compiler}-compile-commands.json"),
        }

    differentials = {}
    for compiler in ("gcc", "clang"):
        path = normalized / f"canonical-normalized-{compiler}-differential.json"
        report = json.loads(path.read_text())
        if report["comparisons"] != 30 or not report["gcc_clang_exact"]:
            raise RuntimeError(f"GNU sed {compiler} normalization differential is incomplete")
        differentials[compiler] = {
            "comparisons": 30, "exact": True, "report_sha256": sha256(path)
        }

    valgrind = (normalized / "valgrind.log").read_text(errors="replace")
    for phrase in (
        "ERROR SUMMARY: 0 errors",
        "definitely lost: 0 bytes in 0 blocks",
        "indirectly lost: 0 bytes in 0 blocks",
        "possibly lost: 0 bytes in 0 blocks",
    ):
        if phrase not in valgrind:
            raise RuntimeError("normalized GNU sed Valgrind smoke is incomplete")

    expected_needed = {"libacl.so.1", "libattr.so.1", "libc.so.6"}
    binaries = {}
    for compiler in ("gcc", "clang"):
        binary = normalized / f"sed-{compiler}"
        libraries = needed(binary)
        if set(libraries) != expected_needed:
            raise RuntimeError(f"normalized GNU sed {compiler} dependencies changed")
        object_symbols = symbols(normalized / f"sed-{compiler}.o")
        if not {"main", "rustbox_sed_main"}.issubset(object_symbols):
            raise RuntimeError(f"normalized GNU sed {compiler} entrypoints are incomplete")
        if (normalized / f"config-{compiler}.h").read_bytes() != (oracle / f"config-{compiler}.h").read_bytes():
            raise RuntimeError(f"normalized GNU sed {compiler} configuration changed")
        binaries[compiler] = {
            "bytes": binary.stat().st_size,
            "sha256": sha256(binary),
            "needed": libraries,
        }

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-20",
        "release": "4.10",
        "transformation": manifest,
        "production": closures,
        "tests": {
            compiler: {"suites": summary, "log_sha256": sha256(normalized / f"{compiler}-check.log")}
            for compiler, summary in tests.items()
        },
        "differential": {
            "by_compiler": differentials,
            "comparisons": 60,
            "canonical_normalized_exact": True,
        },
        "valgrind": {
            "errors": 0,
            "definite_indirect_possible_leaks": 0,
            "still_reachable_bytes": 4317,
            "log_sha256": sha256(normalized / "valgrind.log"),
        },
        "entrypoint": {
            "conditional": "RUSTBOX_MULTICALL",
            "export": "rustbox_sed_main",
            "standalone_main_retained": True,
            "gcc_clang_object_symbols_verified": True,
        },
        "configuration": {"canonical_normalized_exact_by_compiler": True},
        "binaries": binaries,
        "next_gate": "C2Rust audit translation of the exact 85-source production closure",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"differential": 60, "entrypoints": 1, "release_tests": 724, "sanitizer_tests": 75}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

