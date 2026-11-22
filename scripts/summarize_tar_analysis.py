#!/usr/bin/env python3
"""Summarize GNU tar 1.35's production-only five-tool audit."""

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
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/tar-1.35/analyzers"
    names = (
        "compile_commands.json", "sources.list", "c-sources.list",
        "cppcheck.log", "gcc-analyzer.log", "gcc-analyzer.status",
        "clang-analyzer-tidy.log", "clang-analyzer-tidy.status",
        "flawfinder.log", "flawfinder.status", "sparse.log", "sparse.status",
    )
    artifacts = {name: analysis / name for name in names}
    for path in artifacts.values():
        if not path.is_file():
            raise RuntimeError(f"missing GNU tar analyzer artifact: {path}")

    commands = json.loads(artifacts["compile_commands.json"].read_text())
    sources = [line for line in artifacts["sources.list"].read_text().splitlines() if line]
    c_sources = [line for line in artifacts["c-sources.list"].read_text().splitlines() if line]
    if (len(commands), len(sources), len(set(sources)), len(c_sources)) != (197, 197, 197, 197):
        raise RuntimeError("GNU tar analyzer production closure changed")

    cppcheck_text = artifacts["cppcheck.log"].read_text(errors="replace")
    cppcheck_severity = Counter(re.findall(
        r"\.(?:c|h):\d+:\d+: (error|warning|style|performance|portability|information):",
        cppcheck_text,
    ))
    cppcheck_ids = Counter(re.findall(
        r"\.(?:c|h):\d+:\d+: (?:error|warning|style|performance|portability|information): ([A-Za-z0-9_]+):",
        cppcheck_text,
    ))
    expected_cppcheck_severity = {"error": 27, "portability": 1, "style": 327, "warning": 25}
    expected_cppcheck_ids = {
        "allocaCalled": 6, "clarifyCalculation": 11, "clarifyCondition": 4,
        "constParameterCallback": 2, "constParameterPointer": 40,
        "constVariable": 1, "constVariablePointer": 48,
        "duplicateValueTernary": 1, "ignoredReturnValue": 1,
        "integerOverflowCond": 1, "internalAstError": 2,
        "knownConditionTrueFalse": 14, "legacyUninitvar": 1,
        "nullPointerArithmetic": 12, "nullPointerRedundantCheck": 2,
        "preprocessorErrorDirective": 2, "redundantAssignment": 1,
        "redundantContinue": 12, "redundantInitialization": 4,
        "returnDanglingLifetime": 1, "shadowFunction": 3, "shadowVariable": 4,
        "shiftTooManyBitsSigned": 1, "signConversion": 12,
        "signConversionCond": 2, "sizeofwithnumericparameter": 1,
        "unknownEvaluationOrder": 9, "unreadVariable": 5,
        "unsignedLessThanZero": 135, "unsignedPositive": 2,
        "unusedStructMember": 4, "variableScope": 36,
    }
    if dict(sorted(cppcheck_severity.items())) != expected_cppcheck_severity:
        raise RuntimeError(f"GNU tar Cppcheck severity inventory changed: {cppcheck_severity}")
    if dict(sorted(cppcheck_ids.items())) != expected_cppcheck_ids:
        raise RuntimeError(f"GNU tar Cppcheck finding inventory changed: {cppcheck_ids}")

    gcc_text = artifacts["gcc-analyzer.log"].read_text(errors="replace")
    gcc_checks = Counter(re.findall(r"\[-W([^]]+)\]", gcc_text))
    expected_gcc = {
        "analyzer-deref-before-check": 1, "analyzer-fd-leak": 3,
        "analyzer-malloc-leak": 14, "analyzer-null-argument": 1,
        "analyzer-possible-null-argument": 1, "missing-field-initializers": 2,
        "sign-compare": 44, "type-limits": 5, "unused-parameter": 1,
    }
    if dict(sorted(gcc_checks.items())) != expected_gcc:
        raise RuntimeError(f"GNU tar GCC analyzer inventory changed: {gcc_checks}")

    clang_text = artifacts["clang-analyzer-tidy.log"].read_text(errors="replace")
    clang_checks = Counter(re.findall(
        r"\[([A-Za-z][A-Za-z0-9_.-]*-[A-Za-z0-9_.-]+)\]$", clang_text, re.MULTILINE
    ))
    expected_clang = {
        "bugprone-assignment-in-if-condition": 50, "bugprone-branch-clone": 13,
        "bugprone-casting-through-void": 1, "bugprone-easily-swappable-parameters": 81,
        "bugprone-implicit-widening-of-multiplication-result": 15,
        "bugprone-macro-parentheses": 33,
        "bugprone-multi-level-implicit-pointer-conversion": 40,
        "bugprone-narrowing-conversions": 280,
        "bugprone-not-null-terminated-result": 3, "bugprone-reserved-identifier": 68,
        "bugprone-signal-handler": 2, "bugprone-signed-char-misuse": 25,
        "bugprone-sizeof-expression": 13, "bugprone-suspicious-include": 24,
        "bugprone-suspicious-string-compare": 13,
        "bugprone-switch-missing-default-case": 17,
        "clang-analyzer-core.NonNullParamChecker": 7,
        "clang-analyzer-core.NullDereference": 6,
        "clang-analyzer-core.UndefinedBinaryOperatorResult": 1,
        "clang-analyzer-core.uninitialized.Assign": 1,
        "clang-analyzer-core.uninitialized.Branch": 2,
        "clang-analyzer-deadcode.DeadStores": 5,
        "clang-analyzer-optin.portability.UnixAPI": 2,
        "clang-analyzer-security.insecureAPI.DeprecatedOrUnsafeBufferHandling": 243,
        "clang-analyzer-security.insecureAPI.strcpy": 52,
        "clang-analyzer-unix.Malloc": 6,
        "clang-diagnostic-c23-extensions": 11,
        "clang-diagnostic-implicit-const-int-float-conversion": 1,
        "performance-no-int-to-ptr": 4,
    }
    if dict(sorted(clang_checks.items())) != expected_clang:
        raise RuntimeError(f"GNU tar Clang analyzer inventory changed: {clang_checks}")

    flawfinder_text = artifacts["flawfinder.log"].read_text(errors="replace")
    flawfinder_hits = re.search(r"^Hits = (\d+)$", flawfinder_text, re.MULTILINE)
    flawfinder_lines = re.search(r"^Lines analyzed = (\d+) ", flawfinder_text, re.MULTILINE)
    if (not flawfinder_hits or not flawfinder_lines
            or (int(flawfinder_hits[1]), int(flawfinder_lines[1])) != (745, 67055)):
        raise RuntimeError("GNU tar Flawfinder inventory changed")

    sparse_text = artifacts["sparse.log"].read_text(errors="replace")
    sparse_errors = len(re.findall(r" error: ", sparse_text))
    sparse_warnings = len(re.findall(r" warning: ", sparse_text))
    statuses = {
        tool: int(artifacts[f"{tool}.status"].read_text().strip())
        for tool in ("gcc-analyzer", "clang-analyzer-tidy", "flawfinder", "sparse")
    }
    if sparse_errors != 0 or sparse_warnings != 480 or any(statuses.values()):
        raise RuntimeError(
            f"GNU tar analyzer status changed: sparse=({sparse_errors}, {sparse_warnings}), {statuses}"
        )

    oracle = json.loads((repository / "evidence/tar-1.35-oracle.json").read_text())
    if oracle["inventory"]["production_source_count"] != 197:
        raise RuntimeError("GNU tar oracle production closure changed")
    analyzer_checks = {
        name: count for name, count in sorted(clang_checks.items())
        if name.startswith("clang-analyzer-")
    }
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-22",
        "release": "1.35",
        "status": "complete production audit; deterministic normalization in progress",
        "scope": {
            "compile_actions": len(commands), "unique_sources": len(sources),
            "c_sources": len(c_sources), "public_names": ["tar", "rmt"],
            "tests_examples_and_nonselected_sources_excluded": True,
        },
        "tools": {
            "cppcheck": {
                "findings_by_severity": dict(sorted(cppcheck_severity.items())),
                "findings_by_id": dict(sorted(cppcheck_ids.items())),
            },
            "gcc_fanalyzer": {
                "exit_status": statuses["gcc-analyzer"],
                "findings_by_check": dict(sorted(gcc_checks.items())),
            },
            "clang_analyzer_tidy": {
                "exit_status": statuses["clang-analyzer-tidy"],
                "analyzer_findings_by_check": analyzer_checks,
                "all_findings_by_check": dict(sorted(clang_checks.items())),
            },
            "flawfinder": {
                "exit_status": statuses["flawfinder"],
                "hits_at_level_1_or_higher": int(flawfinder_hits[1]),
                "lines_analyzed": int(flawfinder_lines[1]),
            },
            "sparse": {
                "exit_status": statuses["sparse"], "warnings": sparse_warnings,
                "parser_errors": sparse_errors,
                "analyzer_only_compatibility": "spell generated max_align_t scratch storage as same-alignment long double on x86_64",
            },
        },
        "review": {
            "demonstrated_canonical_defects": 0,
            "canonical_source_changes": 0,
            "required_normalization": [
                "Export tar and rmt entrypoints while retaining standalone wrappers.",
                "Keep the complete 197-source configured closure; do not replace gnulib support with translation holes.",
                "Make only translator-required checked widths, ownership, and macro expansions explicit after a failed C2Rust diagnostic demonstrates the need.",
            ],
            "notes": [
                "Cppcheck's error-severity items are inactive portability #error branches, parser failures in generated macro expressions, obstack compile-time branch expansion, and interprocedural preconditions; GCC, Clang, ASan/UBSan, and upstream tests do not corroborate a defect.",
                "The map orig_id report loses the invariant that the only owner/group map callers always pass a nonnull name-to-id function.",
                "GCC allocation reports model returned ownership, xmalloc-family success, registered cleanup, or deliberate process-exit state as leaks; the exact Valgrind baseline is recorded separately.",
                "GCC's sys_exec_info_script fdopen report is an unconfirmed allocation-failure diagnostic gap, not a demonstrated normal-path defect; it remains explicit audit inventory.",
                "Clang's name-list and wordsplit linked-list reports lose same-order and remove/insert invariants; all upstream wordsplit, name-selection, sanitizer, and differential paths pass.",
                "Clang buffer, string, conversion, adjacent-parameter, macro, and dead-store findings are translation inventory, not demonstrated behavioral defects.",
                "Sparse uses the exact configured build through cgcc. Its sole analyzer-only rewrite substitutes long double for generated max_align_t scratch storage; both have 16-byte alignment on the selected x86_64 ABI. It then reports no parser error.",
            ],
        },
        "artifacts": {name: sha256(path) for name, path in artifacts.items()},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "blocking": 0, "clang_analyzer": sum(analyzer_checks.values()),
        "cppcheck": sum(cppcheck_severity.values()),
        "flawfinder": int(flawfinder_hits[1]), "gcc": sum(gcc_checks.values()),
        "sparse_parser_errors": sparse_errors,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
