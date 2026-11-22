#!/usr/bin/env python3
"""Summarize GNU Gawk 5.4.0 production-only static analysis."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "work/analysis/gawk-5.4.0/analyzers"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    names = (
        "compile_commands.json", "sources.list", "cppcheck.log",
        "gcc-analyzer-setup.log", "gcc-analyzer.log",
        "clang-analyzer-tidy.log", "flawfinder.log", "sparse.log", "sparse.status",
    )
    artifacts = {name: ANALYSIS / name for name in names}
    for path in artifacts.values():
        if not path.is_file():
            raise RuntimeError(f"missing GNU Gawk analyzer artifact: {path}")
    commands = json.loads(artifacts["compile_commands.json"].read_text())
    sources = artifacts["sources.list"].read_text().splitlines()
    if len(commands) != 55 or len(sources) != 55 or len(set(sources)) != 55:
        raise RuntimeError("GNU Gawk analyzer production closure changed")

    cppcheck = artifacts["cppcheck.log"].read_text(errors="replace")
    cpp_severity = Counter(re.findall(
        r":\d+:\d+: (error|warning|style|performance|portability|information):", cppcheck
    ))
    cpp_ids = Counter(re.findall(
        r":\d+:\d+: (?:error|warning|style|performance|portability|information): ([A-Za-z0-9_]+):",
        cppcheck,
    ))
    if cpp_severity != {"error": 4} or cpp_ids != {
        "syntaxError": 2, "preprocessorErrorDirective": 2,
    }:
        raise RuntimeError("GNU Gawk Cppcheck parser result changed")

    gcc = artifacts["gcc-analyzer.log"].read_text(errors="replace")
    gcc_checks = Counter(re.findall(r"\[-W([^]]+)\]", gcc))
    expected_gcc = {
        "analyzer-fd-leak": 3, "analyzer-null-argument": 1,
        "analyzer-null-dereference": 3,
        "analyzer-unsafe-call-within-signal-handler": 1,
        "analyzer-use-of-uninitialized-value": 3, "cast-function-type": 3,
        "implicit-fallthrough=": 13, "missing-field-initializers": 9,
        "sign-compare": 138, "unused-parameter": 147,
    }
    if dict(sorted(gcc_checks.items())) != expected_gcc:
        raise RuntimeError(f"GNU Gawk GCC analyzer findings changed: {gcc_checks}")

    clang = artifacts["clang-analyzer-tidy.log"].read_text(errors="replace")
    clang_checks = Counter(re.findall(
        r"\[([A-Za-z][A-Za-z0-9_.-]*-[A-Za-z0-9_.-]+)\]$", clang, re.MULTILINE
    ))
    clang_analyzer = {name: count for name, count in sorted(clang_checks.items())
                      if name.startswith("clang-analyzer-")}
    expected_clang = {
        "clang-analyzer-core.CallAndMessage": 1,
        "clang-analyzer-core.DivideZero": 1,
        "clang-analyzer-core.NonNullParamChecker": 7,
        "clang-analyzer-core.NullDereference": 60,
        "clang-analyzer-deadcode.DeadStores": 26,
        "clang-analyzer-optin.core.EnumCastOutOfRange": 68,
        "clang-analyzer-optin.performance.Padding": 1,
        "clang-analyzer-security.cert.env.InvalidPtr": 1,
        "clang-analyzer-security.insecureAPI.DeprecatedOrUnsafeBufferHandling": 1001,
        "clang-analyzer-security.insecureAPI.strcpy": 22,
    }
    if clang_analyzer != expected_clang:
        raise RuntimeError("GNU Gawk Clang analyzer findings changed")

    flawfinder = artifacts["flawfinder.log"].read_text(errors="replace")
    hits = int(re.search(r"^Hits = (\d+)$", flawfinder, re.MULTILINE).group(1))
    lines = int(re.search(r"^Lines analyzed = (\d+) ", flawfinder, re.MULTILINE).group(1))
    if hits != 627 or lines != 66858:
        raise RuntimeError("GNU Gawk Flawfinder result changed")
    sparse = artifacts["sparse.log"].read_text(errors="replace")
    sparse_errors = len(re.findall(r" error: ", sparse))
    sparse_warnings = len(re.findall(r" warning: ", sparse))
    if sparse_errors != 515 or sparse_warnings != 338:
        raise RuntimeError("GNU Gawk Sparse parser result changed")

    oracle = json.loads((ROOT / "evidence/gawk-5.4.0-oracle.json").read_text())
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-22",
        "release": "5.4.0",
        "scope": {
            "compile_actions": 55, "unique_sources": 55,
            "targets": ["gawk", "awk", "gawkbug", "GNU extension modules"],
        },
        "tools": {
            "cppcheck": {
                "findings_by_severity": dict(sorted(cpp_severity.items())),
                "findings_by_id": dict(sorted(cpp_ids.items())),
            },
            "gcc_fanalyzer": {
                "warnings": sum(gcc_checks.values()),
                "findings_by_check": dict(sorted(gcc_checks.items())),
            },
            "clang_analyzer_tidy": {
                "analyzer_findings_by_check": clang_analyzer,
                "all_findings_by_check": dict(sorted(clang_checks.items())),
            },
            "flawfinder": {"hits_at_level_1_or_higher": hits, "lines_analyzed": lines},
            "sparse": {
                "warnings": sparse_warnings, "parser_errors": sparse_errors,
                "exit_status": int(artifacts["sparse.status"].read_text().strip()),
            },
        },
        "review": {
            "blocking_findings": 1,
            "canonical_source_changes": 0,
            "normalization_targets": [
                "extension/readdir.c flexible-array declaration proven out of bounds by UBSan",
                "export main through a stable multicall entrypoint without changing standalone behavior",
            ],
            "notes": [
                "Cppcheck cannot expand Gawk's generated dynarray macros and configured C89 guard; GCC, Clang, and sanitizer builds are authoritative for those four parser diagnostics.",
                "Sparse lacks the configured generated grammar and macro model; its output is retained as a pointer/type inventory rather than a correctness oracle.",
                "The sanitizer-confirmed readdir field-array declaration is the only demonstrated memory-safety defect and is mandatory normalization work.",
                "GCC descriptor reports cross deliberate ownership transfer through pipe and inplace state; canonical suites and Valgrind cover the exercised lifetimes.",
                "Most Clang null and enum paths lose parser/opcode invariants; they remain recorded for later per-function substitution review rather than being bulk-edited.",
                "Signal-handler and environment-pointer reports identify interfaces that must stay in C residue until a semantics-preserving Rust replacement is proven.",
            ],
            "oracle_differential_passes": oracle["differential"]["passed"],
        },
        "artifacts": {name: sha256(path) for name, path in artifacts.items()},
    }
    output = ROOT / "evidence/gawk-5.4.0-analysis.json"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "clang_analyzer": sum(clang_analyzer.values()), "cppcheck": sum(cpp_severity.values()),
        "flawfinder": hits, "gcc": sum(gcc_checks.values()),
        "sparse_errors": sparse_errors, "sparse_warnings": sparse_warnings,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
