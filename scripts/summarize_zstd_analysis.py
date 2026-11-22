#!/usr/bin/env python3
"""Summarize zstd 1.5.7's production-only static analysis."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/zstd-1.5.7/analyzers"
    names = (
        "compile_commands.json", "sources.list", "c-sources.list",
        "cppcheck.log", "gcc-analyzer.log", "clang-analyzer-tidy.log",
        "clang-analyzer-tidy.status", "flawfinder.log", "flawfinder.status",
        "sparse.log", "sparse.status",
    )
    artifacts = {name: analysis / name for name in names}
    for path in artifacts.values():
        if not path.is_file():
            raise RuntimeError(f"missing zstd analyzer artifact: {path}")

    commands = json.loads(artifacts["compile_commands.json"].read_text())
    sources = [line for line in artifacts["sources.list"].read_text().splitlines() if line]
    c_sources = [line for line in artifacts["c-sources.list"].read_text().splitlines() if line]
    if len(commands) != 45 or len(sources) != 45 or len(set(sources)) != 45 or len(c_sources) != 44:
        raise RuntimeError("zstd analyzer production closure changed")

    cppcheck_text = artifacts["cppcheck.log"].read_text(errors="replace")
    cppcheck_severity = Counter(re.findall(
        r"\.(?:c|h):\d+:\d+: (error|warning|style|performance|portability|information):",
        cppcheck_text,
    ))
    cppcheck_ids = Counter(re.findall(
        r"\.(?:c|h):\d+:\d+: (?:error|warning|style|performance|portability|information): ([A-Za-z0-9_]+):",
        cppcheck_text,
    ))
    expected_cppcheck = {
        "arrayIndexOutOfBoundsCond": 3, "badBitmaskCheck": 1,
        "clarifyCondition": 4, "constParameterCallback": 1,
        "constParameterPointer": 53, "constVariable": 1,
        "constVariablePointer": 69, "duplicateExpression": 1,
        "invalidPrintfArgType_sint": 6, "invalidPrintfArgType_uint": 19,
        "knownConditionTrueFalse": 55, "legacyUninitvar": 1,
        "nullPointerArithmeticRedundantCheck": 1, "nullPointerRedundantCheck": 10,
        "redundantCondition": 2, "redundantContinue": 4,
        "redundantInitialization": 1, "truncLongCastReturn": 5,
        "uninitvar": 4, "unreadVariable": 9, "unsignedLessThanZero": 2,
        "unusedStructMember": 118, "variableScope": 20,
    }
    if dict(sorted(cppcheck_ids.items())) != expected_cppcheck:
        raise RuntimeError(f"zstd Cppcheck findings changed: {cppcheck_ids}")

    gcc_text = artifacts["gcc-analyzer.log"].read_text(errors="replace")
    gcc_checks = Counter(re.findall(r"\[-W([^]]+)\]", gcc_text))
    expected_gcc = {
        "analyzer-malloc-leak": 2, "analyzer-out-of-bounds": 3,
        "analyzer-use-of-uninitialized-value": 1,
    }
    if dict(sorted(gcc_checks.items())) != expected_gcc:
        raise RuntimeError(f"zstd GCC analyzer findings changed: {gcc_checks}")

    clang_text = artifacts["clang-analyzer-tidy.log"].read_text(errors="replace")
    clang_checks = Counter(re.findall(
        r"\[([A-Za-z][A-Za-z0-9_.-]*-[A-Za-z0-9_.-]+)\]$", clang_text, re.MULTILINE
    ))
    expected_clang = {
        "bugprone-assignment-in-if-condition": 31, "bugprone-branch-clone": 13,
        "bugprone-casting-through-void": 2, "bugprone-easily-swappable-parameters": 540,
        "bugprone-implicit-widening-of-multiplication-result": 131,
        "bugprone-inc-dec-in-conditions": 19, "bugprone-macro-parentheses": 302,
        "bugprone-misplaced-widening-cast": 1,
        "bugprone-multi-level-implicit-pointer-conversion": 7,
        "bugprone-narrowing-conversions": 141, "bugprone-not-null-terminated-result": 4,
        "bugprone-reserved-identifier": 55, "bugprone-signal-handler": 9,
        "bugprone-suspicious-string-compare": 10,
        "bugprone-switch-missing-default-case": 5,
        "clang-analyzer-core.BitwiseShift": 1,
        "clang-analyzer-core.NonNullParamChecker": 5,
        "clang-analyzer-core.NullDereference": 1,
        "clang-analyzer-core.UndefinedBinaryOperatorResult": 1,
        "clang-analyzer-core.uninitialized.Assign": 1,
        "clang-analyzer-deadcode.DeadStores": 7,
        "clang-analyzer-optin.core.EnumCastOutOfRange": 1,
        "clang-analyzer-optin.portability.UnixAPI": 6,
        "clang-analyzer-security.insecureAPI.DeprecatedOrUnsafeBufferHandling": 1358,
        "clang-analyzer-security.insecureAPI.strcpy": 1,
        "clang-diagnostic-error": 8, "clang-diagnostic-implicit-int": 1,
        "clang-diagnostic-strict-prototypes": 1, "performance-no-int-to-ptr": 12,
    }
    if dict(sorted(clang_checks.items())) != expected_clang:
        raise RuntimeError(f"zstd Clang findings changed: {clang_checks}")

    flawfinder_text = artifacts["flawfinder.log"].read_text(errors="replace")
    flawfinder_hits = re.search(r"^Hits = (\d+)$", flawfinder_text, re.MULTILINE)
    flawfinder_lines = re.search(r"^Lines analyzed = (\d+) ", flawfinder_text, re.MULTILINE)
    if (not flawfinder_hits or not flawfinder_lines
            or int(flawfinder_hits[1]) != 191 or int(flawfinder_lines[1]) != 56046):
        raise RuntimeError("zstd Flawfinder summary changed")

    sparse_text = artifacts["sparse.log"].read_text(errors="replace")
    sparse_errors = len(re.findall(r" error: ", sparse_text))
    sparse_warnings = len(re.findall(r" warning: ", sparse_text))
    sparse_status = int(artifacts["sparse.status"].read_text().strip())
    if (sparse_errors, sparse_warnings, sparse_status) != (0, 13, 0):
        raise RuntimeError("zstd Sparse inventory changed")

    oracle = json.loads((repository / "evidence/zstd-1.5.7-oracle.json").read_text())
    if oracle["inventory"]["production_source_count"] != 45:
        raise RuntimeError("zstd oracle production closure changed")

    analyzer_checks = {name: count for name, count in sorted(clang_checks.items())
                       if name.startswith("clang-analyzer-")}
    evidence = {
        "schema": 1, "recorded_at": "2026-11-22", "release": "1.5.7",
        "status": "complete production audit; deterministic normalization pending",
        "scope": {
            "compile_actions": len(commands), "unique_sources": len(sources),
            "c_sources": len(c_sources), "assembly_sources": 1,
            "public_names": oracle["inventory"]["public_names"],
            "tests_examples_and_nonselected_sources_excluded": True,
        },
        "tools": {
            "cppcheck": {"findings_by_severity": dict(sorted(cppcheck_severity.items())),
                         "findings_by_id": dict(sorted(cppcheck_ids.items()))},
            "gcc_fanalyzer": {"warnings": sum(gcc_checks.values()),
                              "findings_by_check": dict(sorted(gcc_checks.items()))},
            "clang_analyzer_tidy": {
                "wrapper_exit_status": int(artifacts["clang-analyzer-tidy.status"].read_text()),
                "analyzer_findings_by_check": analyzer_checks,
                "all_findings_by_check": dict(sorted(clang_checks.items())),
                "assembly_parse_diagnostics": 10,
            },
            "flawfinder": {"hits_at_level_1_or_higher": int(flawfinder_hits[1]),
                           "lines_analyzed": int(flawfinder_lines[1])},
            "sparse": {"warnings": sparse_warnings, "parser_errors": sparse_errors,
                       "exit_status": sparse_status},
        },
        "review": {
            "demonstrated_canonical_defects": 0,
            "canonical_source_changes": 0,
            "required_normalization": [
                "Export zstd's physical CLI entrypoint while retaining a standalone wrapper.",
                "Select upstream portable C Huffman decoding instead of x86-64 assembly for C2Rust.",
                "Retain the canonical self-contained configuration without optional foreign-format libraries.",
            ],
            "notes": [
                "The Clang wrapper status is caused by treating the selected preprocessed assembly unit as C; the native compiler and upstream tests assemble it successfully, and translation selects the upstream portable C path.",
                "Cppcheck uninitialized-field reports cross tagged-struct or successful-return invariants; the complete GCC, Clang, and sanitizer suites exercise these paths without a failure.",
                "GCC cover/benchmark reports follow allocation-failure or loop-bound paths that conflict with checked allocation and count invariants; no paired sanitizer, Clang, or upstream failure demonstrates them.",
                "GCC's zstdmt leak report follows ownership transfer into the thread-pool job structure; upstream resource tests and Valgrind show no lost allocation.",
                "Clang buffer-API, macro, conversion, adjacent-parameter, and dead-store findings are translation inventory, not demonstrated behavioral defects.",
                "Sparse reports only address-space and non-ANSI constant-expression warnings; it reports no parser error in the C closure.",
            ],
        },
        "artifacts": {name: sha256(path) for name, path in artifacts.items()},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"blocking": 0, "clang_analyzer": sum(analyzer_checks.values()),
                      "cppcheck": sum(cppcheck_severity.values()),
                      "flawfinder": int(flawfinder_hits[1]),
                      "gcc": sum(gcc_checks.values()),
                      "sparse_parser_errors": sparse_errors}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
