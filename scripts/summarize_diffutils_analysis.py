#!/usr/bin/env python3
"""Summarize GNU Diffutils 3.12 production-only static analysis."""

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
    analysis = repository / "work/analysis/diffutils-3.12/analyzers"
    names = (
        "compile_commands.json", "sources.list", "cppcheck.log",
        "gcc-analyzer-setup.log", "gcc-analyzer.log",
        "clang-analyzer-tidy.log", "flawfinder.log", "sparse.log", "sparse.status",
    )
    artifacts = {name: analysis / name for name in names}
    for path in artifacts.values():
        if not path.is_file():
            raise RuntimeError(f"missing GNU Diffutils analyzer artifact: {path}")

    commands = json.loads(artifacts["compile_commands.json"].read_text())
    sources = [line for line in artifacts["sources.list"].read_text().splitlines() if line]
    if len(commands) != 139 or len(sources) != 139 or len(set(sources)) != 139:
        raise RuntimeError("GNU Diffutils analyzer production closure changed")

    cppcheck_text = artifacts["cppcheck.log"].read_text(errors="replace")
    cppcheck_severity = Counter(re.findall(
        r"\.c:\d+:\d+: (error|warning|style|performance|portability|information):",
        cppcheck_text,
    ))
    cppcheck_ids = Counter(re.findall(
        r"\.c:\d+:\d+: (?:error|warning|style|performance|portability|information): ([A-Za-z0-9_]+):",
        cppcheck_text,
    ))
    expected_cppcheck = {
        "allocaCalled": 1, "clarifyCalculation": 3, "clarifyCondition": 8,
        "constParameterPointer": 6, "constVariablePointer": 14,
        "invalidPrintfArgType_sint": 4, "invalidPrintfArgType_uint": 1,
        "knownConditionTrueFalse": 11, "leakReturnValNotUsed": 1,
        "nullPointerRedundantCheck": 1, "objectIndex": 7, "pointerSize": 3,
        "preprocessorErrorDirective": 1, "redundantContinue": 20,
        "returnNonBoolInBooleanFunction": 1, "shadowVariable": 1,
        "unassignedVariable": 1, "unreadVariable": 5,
        "unsignedLessThanZero": 1, "unusedStructMember": 2,
    }
    if dict(sorted(cppcheck_ids.items())) != expected_cppcheck:
        raise RuntimeError(f"GNU Diffutils Cppcheck findings changed: {cppcheck_ids}")

    gcc_text = artifacts["gcc-analyzer.log"].read_text(errors="replace")
    gcc_checks = Counter(re.findall(r"\[-W([^]]+)\]", gcc_text))
    expected_gcc = {
        "analyzer-fd-leak": 3,
        "analyzer-malloc-leak": 14,
        "sign-compare": 18,
    }
    if dict(sorted(gcc_checks.items())) != expected_gcc:
        raise RuntimeError(f"GNU Diffutils GCC analyzer findings changed: {gcc_checks}")

    clang_text = artifacts["clang-analyzer-tidy.log"].read_text(errors="replace")
    clang_checks = Counter(re.findall(
        r"\[([A-Za-z][A-Za-z0-9_.-]*-[A-Za-z0-9_.-]+)\]$", clang_text, re.MULTILINE
    ))
    clang_analyzer = {
        name: count for name, count in sorted(clang_checks.items())
        if name.startswith("clang-analyzer-")
    }
    expected_clang_analyzer = {
        "clang-analyzer-core.NonNullParamChecker": 1,
        "clang-analyzer-core.NullDereference": 2,
        "clang-analyzer-deadcode.DeadStores": 1,
        "clang-analyzer-security.insecureAPI.DeprecatedOrUnsafeBufferHandling": 137,
        "clang-analyzer-security.insecureAPI.strcpy": 6,
        "clang-analyzer-unix.Malloc": 3,
    }
    if clang_analyzer != expected_clang_analyzer:
        raise RuntimeError(f"GNU Diffutils Clang analyzer findings changed: {clang_analyzer}")

    flawfinder_text = artifacts["flawfinder.log"].read_text(errors="replace")
    flawfinder_hits = re.search(r"^Hits = (\d+)$", flawfinder_text, re.MULTILINE)
    flawfinder_lines = re.search(r"^Lines analyzed = (\d+) ", flawfinder_text, re.MULTILINE)
    if not flawfinder_hits or not flawfinder_lines or int(flawfinder_hits.group(1)) != 285:
        raise RuntimeError("GNU Diffutils Flawfinder summary changed")

    sparse_text = artifacts["sparse.log"].read_text(errors="replace")
    sparse_errors = len(re.findall(r" error: ", sparse_text))
    sparse_warnings = len(re.findall(r" warning: ", sparse_text))
    if sparse_errors != 20 or sparse_warnings != 141:
        raise RuntimeError(f"GNU Diffutils Sparse output changed: {sparse_errors}/{sparse_warnings}")

    oracle = json.loads((repository / "evidence/diffutils-3.12-oracle.json").read_text())
    if oracle["scope"]["normal_production_sources"] != 139:
        raise RuntimeError("GNU Diffutils oracle production closure changed")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-20",
        "release": "3.12",
        "scope": {
            "compile_actions": len(commands),
            "unique_sources": len(sources),
            "targets": ["cmp", "diff", "diff3", "sdiff"],
            "tests_examples_and_sanitizer_only_replacements_excluded": True,
        },
        "tools": {
            "cppcheck": {
                "findings_by_severity": dict(sorted(cppcheck_severity.items())),
                "findings_by_id": dict(sorted(cppcheck_ids.items())),
            },
            "gcc_fanalyzer": {
                "warnings": sum(gcc_checks.values()),
                "findings_by_check": dict(sorted(gcc_checks.items())),
            },
            "clang_analyzer_tidy": {
                "analyzer_findings_by_check": clang_analyzer,
                "all_findings_by_check": dict(sorted(clang_checks.items())),
            },
            "flawfinder": {
                "hits_at_level_1_or_higher": int(flawfinder_hits.group(1)),
                "lines_analyzed": int(flawfinder_lines.group(1)),
            },
            "sparse": {
                "warnings": sparse_warnings,
                "parser_errors": sparse_errors,
                "exit_status": int(artifacts["sparse.status"].read_text().strip()),
            },
        },
        "review": {
            "blocking_findings": 0,
            "canonical_source_changes": 0,
            "known_canonical_resource_baseline": {
                "diff3_definitely_lost_bytes": 4096,
                "diff3_possibly_lost_bytes": 4096,
            },
            "notes": [
                "Cppcheck's chdir-long preprocessor error analyzes a configure guard without the selected config; the production compiler selects the valid branch.",
                "Cppcheck's side.c objectIndex analysis mistakes curr.file[*].linbuf for a local object and loses the paired start/end-pointer representation; upstream and differential side-by-side tests exercise these paths under sanitizers.",
                "Cppcheck's xfreopen allocation-return warning treats freopen as an allocator; successful freopen intentionally reuses FP and failure exits through error.",
                "GCC's stdopen descriptor leaks are the function's purpose: newly opened descriptors occupy missing standard descriptor numbers 0 through 2 and remain process-owned.",
                "GCC's xmalloc-family reports model allocation-returning helpers as leaks at return; ownership is transferred to callers.  exclude.c similarly transfers a unique string to its hash table.",
                "GCC's generated xpalloc reports likewise stop at an allocation-returning helper; diff.c keeps its regex fastmap in process-lifetime global state, and analyze.c frees the original allocation after temporarily offsetting both work pointers.",
                "GCC and Clang time_rz reports do not follow revert_tz, which restores the environment and calls tzfree on every old_tz success path.",
                "Clang's two diff3 null reports lose create_diff3_block's line-count invariant: a line array is allocated exactly when the associated loop can execute.",
                "Clang's diff.c nonnull report does not model xpalloc as non-returning on allocation failure; the size<=newlen branch allocates at least one byte before memcpy.",
                "The canonical diff3 Valgrind buffer retention is preserved as an explicit oracle baseline; normalization and translation may not introduce additional loss.",
                "Remaining Clang-Tidy and Flawfinder results are portability, buffer-hardening, and pointer-modernization inventory rather than demonstrated defects.",
                "Sparse parser errors arise from configured gnulib headers, attributes, and C23 syntax outside its grammar and are recorded rather than suppressed.",
            ],
        },
        "artifacts": {name: sha256(path) for name, path in artifacts.items()},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "clang_analyzer": sum(clang_analyzer.values()),
        "cppcheck": sum(cppcheck_severity.values()),
        "flawfinder": int(flawfinder_hits.group(1)),
        "gcc": sum(gcc_checks.values()),
        "sparse_parser_errors": sparse_errors,
        "sparse_warnings": sparse_warnings,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
