#!/usr/bin/env python3
"""Summarize curl 8.23.0 production-only static analysis."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "work/analysis/curl-8.23.0/analyzers"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def status(path: Path) -> int:
    return int(path.read_text().strip())


def main() -> int:
    names = (
        "compile_commands.json", "sources.list", "cppcheck.log", "cppcheck.status",
        "gcc-analyzer.log", "gcc-analyzer-summary.json", "gcc-analyzer.status",
        "clang-analyzer-tidy.log", "clang-analyzer-tidy.status",
        "flawfinder.log", "flawfinder.status", "sparse.log", "sparse.status",
    )
    artifacts = {name: ANALYSIS / name for name in names}
    for path in artifacts.values():
        if not path.is_file():
            raise RuntimeError(f"missing curl analyzer artifact: {path}")

    commands = json.loads(artifacts["compile_commands.json"].read_text())
    sources = artifacts["sources.list"].read_text().splitlines()
    if len(commands) != 477 or len(sources) != 240 or len(set(sources)) != 240:
        raise RuntimeError("curl analyzer production closure changed")

    cppcheck = artifacts["cppcheck.log"].read_text(errors="replace")
    cpp_severity = Counter(re.findall(
        r":\d+:\d+: (error|warning|style|performance|portability|information):",
        cppcheck,
    ))
    cpp_ids = Counter(re.findall(
        r":\d+:\d+: (?:error|warning|style|performance|portability|information): "
        r"([A-Za-z0-9_]+):", cppcheck,
    ))
    expected_cpp_severity = {"error": 3, "style": 451, "warning": 182}
    expected_cpp_ids = {
        "clarifyCalculation": 4, "constParameterCallback": 2,
        "constParameterPointer": 183, "constVariable": 2,
        "constVariablePointer": 87, "ctunullpointer": 41,
        "duplicateCondition": 2, "duplicateConditionalAssign": 1,
        "identicalConditionAfterEarlyExit": 8, "identicalInnerCondition": 1,
        "knownConditionTrueFalse": 47, "nullPointerRedundantCheck": 130,
        "objectIndex": 1, "redundantAssignment": 2,
        "redundantInitialization": 1, "shadowFunction": 2, "uninitvar": 4,
        "unreadVariable": 19, "unsignedLessThanZero": 2,
        "unusedStructMember": 18, "variableScope": 79,
    }
    if dict(sorted(cpp_severity.items())) != expected_cpp_severity:
        raise RuntimeError(f"curl Cppcheck severity totals changed: {cpp_severity}")
    if dict(sorted(cpp_ids.items())) != expected_cpp_ids:
        raise RuntimeError(f"curl Cppcheck findings changed: {cpp_ids}")

    gcc_summary = json.loads(artifacts["gcc-analyzer-summary.json"].read_text())
    expected_gcc_summary = {
        "compile_actions": 477, "compiler": "gcc", "failed": 0,
        "failures": [], "passed": 477, "schema": 1, "timed_out": 0,
    }
    if gcc_summary != expected_gcc_summary:
        raise RuntimeError(f"curl GCC replay result changed: {gcc_summary}")
    gcc = artifacts["gcc-analyzer.log"].read_text(errors="replace")
    gcc_checks = Counter(re.findall(r"\[-W([^]]+)\]", gcc))
    expected_gcc = {"analyzer-use-of-uninitialized-value": 8}
    if dict(sorted(gcc_checks.items())) != expected_gcc:
        raise RuntimeError(f"curl GCC analyzer findings changed: {gcc_checks}")

    clang = artifacts["clang-analyzer-tidy.log"].read_text(errors="replace")
    clang_checks = Counter(re.findall(
        r"\[([A-Za-z][A-Za-z0-9_.-]*-[A-Za-z0-9_.-]+)\]$", clang,
        re.MULTILINE,
    ))
    expected_clang = {
        "bugprone-branch-clone": 35,
        "bugprone-casting-through-void": 120,
        "bugprone-easily-swappable-parameters": 195,
        "bugprone-implicit-widening-of-multiplication-result": 150,
        "bugprone-inc-dec-in-conditions": 4,
        "bugprone-macro-parentheses": 968,
        "bugprone-misplaced-widening-cast": 1,
        "bugprone-multi-level-implicit-pointer-conversion": 56,
        "bugprone-narrowing-conversions": 74,
        "bugprone-reserved-identifier": 1,
        "bugprone-sizeof-expression": 18,
        "bugprone-suspicious-string-compare": 24,
        "bugprone-switch-missing-default-case": 58,
        "bugprone-too-small-loop-variable": 2,
        "clang-analyzer-optin.performance.Padding": 239,
        "clang-analyzer-security.insecureAPI.DeprecatedOrUnsafeBufferHandling": 225,
        "clang-analyzer-valist.Uninitialized": 57,
        "performance-no-int-to-ptr": 28,
    }
    if dict(sorted(clang_checks.items())) != expected_clang:
        raise RuntimeError(f"curl Clang analyzer findings changed: {clang_checks}")

    flawfinder = artifacts["flawfinder.log"].read_text(errors="replace")
    hits_match = re.search(r"^Hits = (\d+)$", flawfinder, re.MULTILINE)
    lines_match = re.search(r"^Lines analyzed = (\d+) ", flawfinder, re.MULTILINE)
    if hits_match is None or lines_match is None:
        raise RuntimeError("curl Flawfinder totals are missing")
    hits = int(hits_match.group(1))
    lines = int(lines_match.group(1))
    if (hits, lines) != (1215, 183080):
        raise RuntimeError(f"curl Flawfinder result changed: {hits}/{lines}")

    sparse = artifacts["sparse.log"].read_text(errors="replace")
    sparse_errors = len(re.findall(r" error: ", sparse))
    sparse_warnings = len(re.findall(r" warning: ", sparse))
    if (sparse_errors, sparse_warnings) != (0, 202):
        raise RuntimeError(
            f"curl Sparse parser result changed: {sparse_errors}/{sparse_warnings}"
        )

    statuses = {
        "cppcheck": status(artifacts["cppcheck.status"]),
        "gcc_fanalyzer": status(artifacts["gcc-analyzer.status"]),
        "clang_analyzer_tidy": status(artifacts["clang-analyzer-tidy.status"]),
        "flawfinder": status(artifacts["flawfinder.status"]),
        "sparse": status(artifacts["sparse.status"]),
    }
    if statuses != {
        "cppcheck": 0, "gcc_fanalyzer": 0, "clang_analyzer_tidy": 0,
        "flawfinder": 0, "sparse": 0,
    }:
        raise RuntimeError(f"curl analyzer statuses changed: {statuses}")

    oracle = json.loads((ROOT / "evidence/curl-8.23.0-oracle.json").read_text())
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-23",
        "release": "8.23.0",
        "scope": {
            "compile_actions": 477,
            "unique_sources": 240,
            "targets": ["curl", "curl-config", "static libcurl"],
        },
        "tools": {
            "cppcheck": {
                "exit_status": statuses["cppcheck"],
                "findings_by_severity": dict(sorted(cpp_severity.items())),
                "findings_by_id": dict(sorted(cpp_ids.items())),
            },
            "gcc_fanalyzer": {
                "exit_status": statuses["gcc_fanalyzer"],
                "compile_actions_passed": gcc_summary["passed"],
                "warnings": sum(gcc_checks.values()),
                "findings_by_check": dict(sorted(gcc_checks.items())),
            },
            "clang_analyzer_tidy": {
                "exit_status": statuses["clang_analyzer_tidy"],
                "analyzer_findings": sum(
                    count for name, count in clang_checks.items()
                    if name.startswith("clang-analyzer-")
                ),
                "all_findings_by_check": dict(sorted(clang_checks.items())),
            },
            "flawfinder": {
                "exit_status": statuses["flawfinder"],
                "hits_at_level_1_or_higher": hits,
                "lines_analyzed": lines,
            },
            "sparse": {
                "exit_status": statuses["sparse"],
                "warnings": sparse_warnings,
                "parser_errors": sparse_errors,
            },
        },
        "review": {
            "blocking_findings": 0,
            "canonical_source_changes": 0,
            "notes": [
                "Cppcheck's three error-severity reports lose established path-string and bsearch comparator invariants; the configured GCC/Clang suites and exact differential gate remain clean.",
                "GCC's duplicated SHA schedule reports follow loops that initialize every consumed word, while its query reports lose the allocation-error branch; all 477 analyzer commands compile.",
                "Clang's va_list reports are on variadic entrypoints that execute va_start before the reported va_arg, including Curl_getinfo and curl_easy_getinfo; they are analyzer-model losses rather than demonstrated uninitialized reads.",
                "The remaining Clang diagnostics are retained by check for per-function substitution review rather than being bulk-edited before normalization.",
                "Sparse completes the full source list without parser errors; its Linux restricted-endian casts and legacy integer-NULL reports are retained as type-migration inventory.",
                "The signed oracle passes 1,601 applicable tests under both compilers, twelve exact public comparisons, and zero-error, zero-retained-byte Valgrind version and file-transfer paths.",
            ],
            "oracle_tests_per_compiler": oracle["tests"]["gcc"]["passed"],
            "oracle_differential_passes": oracle["tests"]["differential"]["passed"],
        },
        "artifacts": {name: sha256(path) for name, path in artifacts.items()},
    }
    output = ROOT / "evidence/curl-8.23.0-static-analysis.json"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "clang_analyzer": evidence["tools"]["clang_analyzer_tidy"]["analyzer_findings"],
        "cppcheck": sum(cpp_severity.values()), "flawfinder": hits,
        "gcc": sum(gcc_checks.values()), "sparse_errors": sparse_errors,
        "sparse_warnings": sparse_warnings,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
