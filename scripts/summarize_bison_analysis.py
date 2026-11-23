#!/usr/bin/env python3
"""Summarize GNU Bison 3.8.2 production-only static analysis."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "work/analysis/bison-3.8.2/analyzers"


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
            raise RuntimeError(f"missing GNU Bison analyzer artifact: {path}")

    commands = json.loads(artifacts["compile_commands.json"].read_text())
    sources = artifacts["sources.list"].read_text().splitlines()
    if len(commands) != 152 or len(sources) != 152 or len(set(sources)) != 152:
        raise RuntimeError("GNU Bison analyzer production closure changed")

    cppcheck = artifacts["cppcheck.log"].read_text(errors="replace")
    cpp_severity = Counter(re.findall(
        r":\d+:\d+: (error|warning|style|performance|portability|information):", cppcheck
    ))
    cpp_ids = Counter(re.findall(
        r":\d+:\d+: (?:error|warning|style|performance|portability|information): "
        r"([A-Za-z0-9_]+):", cppcheck,
    ))
    expected_cpp_ids = {
        "allocaCalled": 1, "arrayIndexOutOfBoundsCond": 1, "clarifyCalculation": 1,
        "clarifyCondition": 2, "constParameter": 1, "constParameterCallback": 2,
        "constParameterPointer": 35, "constVariablePointer": 88, "cppcheckError": 1,
        "internalAstError": 1, "invalidPrintfArgType_sint": 4,
        "invalidPrintfArgType_uint": 3, "knownConditionTrueFalse": 8, "memleak": 1,
        "nullPointer": 6, "nullPointerArithmetic": 112,
        "nullPointerRedundantCheck": 2, "redundantAssignment": 4,
        "redundantContinue": 20, "redundantInitialization": 4,
        "returnNonBoolInBooleanFunction": 2, "uninitvar": 9,
        "unreadVariable": 5, "unsignedLessThanZero": 7, "unusedStructMember": 5,
        "uselessAssignmentPtrArg": 2, "variableScope": 6,
    }
    if cpp_severity != {"error": 121, "warning": 20, "style": 190, "portability": 2}:
        raise RuntimeError(f"GNU Bison Cppcheck severity totals changed: {cpp_severity}")
    if dict(sorted(cpp_ids.items())) != expected_cpp_ids:
        raise RuntimeError(f"GNU Bison Cppcheck findings changed: {cpp_ids}")
    if "152/152 files checked" not in cppcheck or "src/strversion.c" not in cppcheck:
        raise RuntimeError("GNU Bison bounded Cppcheck coverage changed")

    gcc_summary = json.loads(artifacts["gcc-analyzer-summary.json"].read_text())
    expected_gcc_summary = {
        "compile_actions": 152, "compiler": "gcc", "failed": 0, "failures": [],
        "passed": 152, "schema": 1, "timed_out": 0,
    }
    if gcc_summary != expected_gcc_summary:
        raise RuntimeError(f"GNU Bison GCC replay result changed: {gcc_summary}")
    gcc = artifacts["gcc-analyzer.log"].read_text(errors="replace")
    gcc_checks = Counter(re.findall(r"\[-W([^]]+)\]", gcc))
    expected_gcc = {
        "analyzer-fd-double-close": 1, "analyzer-malloc-leak": 33,
        "analyzer-null-argument": 1, "analyzer-null-dereference": 3,
        "analyzer-possible-null-dereference": 5,
        "analyzer-use-of-uninitialized-value": 15, "cpp": 4,
        "maybe-uninitialized": 3, "return-local-addr": 1, "sign-compare": 49,
        "unused-parameter": 1,
    }
    if dict(sorted(gcc_checks.items())) != expected_gcc:
        raise RuntimeError(f"GNU Bison GCC analyzer findings changed: {gcc_checks}")

    clang = artifacts["clang-analyzer-tidy.log"].read_text(errors="replace")
    clang_checks = Counter(re.findall(
        r"\[([A-Za-z][A-Za-z0-9_.-]*-[A-Za-z0-9_.-]+)\]$", clang, re.MULTILINE
    ))
    expected_clang = {
        "bugprone-assignment-in-if-condition": 49, "bugprone-branch-clone": 5,
        "bugprone-casting-through-void": 4, "bugprone-easily-swappable-parameters": 319,
        "bugprone-macro-parentheses": 1290, "bugprone-misplaced-widening-cast": 9,
        "bugprone-multi-level-implicit-pointer-conversion": 113,
        "bugprone-narrowing-conversions": 125, "bugprone-not-null-terminated-result": 1,
        "bugprone-reserved-identifier": 3798, "bugprone-signed-char-misuse": 14,
        "bugprone-sizeof-expression": 35, "bugprone-suspicious-include": 4,
        "bugprone-suspicious-missing-comma": 1,
        "bugprone-suspicious-string-compare": 7,
        "bugprone-switch-missing-default-case": 9,
        "clang-analyzer-core.NonNullParamChecker": 1,
        "clang-analyzer-core.NullDereference": 4,
        "clang-analyzer-deadcode.DeadStores": 7,
        "clang-analyzer-optin.core.EnumCastOutOfRange": 10,
        "clang-analyzer-optin.portability.UnixAPI": 2,
        "clang-analyzer-security.insecureAPI.DeprecatedOrUnsafeBufferHandling": 749,
        "clang-analyzer-security.insecureAPI.strcpy": 2,
        "performance-no-int-to-ptr": 28,
    }
    if dict(sorted(clang_checks.items())) != expected_clang:
        raise RuntimeError(f"GNU Bison Clang analyzer findings changed: {clang_checks}")

    flawfinder = artifacts["flawfinder.log"].read_text(errors="replace")
    hits = int(re.search(r"^Hits = (\d+)$", flawfinder, re.MULTILINE).group(1))
    lines = int(re.search(r"^Lines analyzed = (\d+) ", flawfinder, re.MULTILINE).group(1))
    if (hits, lines) != (306, 51598):
        raise RuntimeError(f"GNU Bison Flawfinder result changed: {hits}/{lines}")

    sparse = artifacts["sparse.log"].read_text(errors="replace")
    sparse_errors = len(re.findall(r" error: ", sparse))
    sparse_warnings = len(re.findall(r" warning: ", sparse))
    if (sparse_errors, sparse_warnings) != (62, 489):
        raise RuntimeError(
            f"GNU Bison Sparse parser result changed: {sparse_errors}/{sparse_warnings}"
        )

    statuses = {
        "cppcheck": status(artifacts["cppcheck.status"]),
        "gcc_fanalyzer": status(artifacts["gcc-analyzer.status"]),
        "clang_analyzer_tidy": status(artifacts["clang-analyzer-tidy.status"]),
        "flawfinder": status(artifacts["flawfinder.status"]),
        "sparse": status(artifacts["sparse.status"]),
    }
    if statuses != {
        "cppcheck": 124, "gcc_fanalyzer": 0, "clang_analyzer_tidy": 0,
        "flawfinder": 0, "sparse": 0,
    }:
        raise RuntimeError(f"GNU Bison analyzer statuses changed: {statuses}")

    oracle = json.loads((ROOT / "evidence/bison-3.8.2-oracle.json").read_text())
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-23",
        "release": "3.8.2",
        "scope": {
            "compile_actions": 152, "unique_sources": 152,
            "targets": ["bison", "yacc", "C skeletons", "C++ skeletons"],
        },
        "tools": {
            "cppcheck": {
                "exit_status": statuses["cppcheck"], "files_reached": 152,
                "bounded_exception": "src/strversion.c child terminated after reproducible nontermination",
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
                "hits_at_level_1_or_higher": hits, "lines_analyzed": lines,
            },
            "sparse": {
                "exit_status": statuses["sparse"],
                "warnings": sparse_warnings, "parser_errors": sparse_errors,
            },
        },
        "review": {
            "blocking_findings": 0,
            "canonical_source_changes": 0,
            "notes": [
                "Cppcheck reaches every production file but its strversion.c child does not terminate; the bounded run records the resulting internal error instead of hanging the workflow.",
                "GCC analysis replays the exact verified 152-command Clang database so generated headers and production defines remain identical; every replay action compiles.",
                "Generated Flex scanners and Bison parsers account for the conditional array/null diagnostics; five generated parser families and the full in-scope upstream suite pass.",
                "Gnulib ownership-transfer reports are retained for per-function Rust substitution review; the final multicall is clean under its canonical Valgrind gate.",
                "Sparse lacks the generated parser state model and is retained as a pointer/type inventory rather than a correctness oracle.",
            ],
            "oracle_differential_passes": oracle["differential"]["passed"],
            "oracle_generated_parsers": oracle["differential"]["compiled_parsers"],
        },
        "artifacts": {name: sha256(path) for name, path in artifacts.items()},
    }
    output = ROOT / "evidence/bison-3.8.2-static-analysis.json"
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
