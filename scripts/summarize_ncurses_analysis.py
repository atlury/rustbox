#!/usr/bin/env python3
"""Summarize Ncurses 6.6's production-only five-tool audit."""

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
    analysis = repository / "work/analysis/ncurses-6.6/analyzers"
    names = (
        "compile_commands.json", "sources.list", "cppcheck.log",
        "gcc-analyzer.log", "gcc-analyzer.status", "clang-analyzer-tidy.log",
        "clang-analyzer-tidy.status", "flawfinder.log", "flawfinder.status",
        "sparse.log", "sparse.status",
    )
    artifacts = {name: analysis / name for name in names}
    for path in artifacts.values():
        if not path.is_file():
            raise RuntimeError(f"missing Ncurses analyzer artifact: {path}")

    commands = json.loads(artifacts["compile_commands.json"].read_text())
    sources = [line for line in artifacts["sources.list"].read_text().splitlines() if line]
    if (len(commands), len(sources), len(set(sources))) != (264, 264, 264):
        raise RuntimeError("Ncurses analyzer production closure changed")

    cppcheck_text = artifacts["cppcheck.log"].read_text(errors="replace")
    cppcheck_severity = Counter(re.findall(
        r"\.(?:c|h):\d+:\d+: (error|warning|style|performance|portability|information):",
        cppcheck_text,
    ))
    cppcheck_ids = Counter(re.findall(
        r"\.(?:c|h):\d+:\d+: (?:error|warning|style|performance|portability|information): ([A-Za-z0-9_]+):",
        cppcheck_text,
    ))
    expected_cppcheck_severity = {"error": 9, "style": 96, "warning": 15}
    expected_cppcheck_ids = {
        "constParameter": 1, "constParameterPointer": 32,
        "constVariablePointer": 8, "doubleFree": 8,
        "duplicateCondition": 1, "duplicateExpression": 3,
        "knownConditionTrueFalse": 9, "nullPointerArithmeticRedundantCheck": 1,
        "nullPointerRedundantCheck": 13, "redundantAssignment": 9,
        "redundantContinue": 1, "redundantPointerOp": 9,
        "uninitvar": 1, "unknownMacro": 1, "unreadVariable": 7,
        "unsignedLessThanZero": 7, "unusedStructMember": 3, "variableScope": 6,
    }
    if dict(sorted(cppcheck_severity.items())) != expected_cppcheck_severity:
        raise RuntimeError(f"Ncurses Cppcheck severity inventory changed: {cppcheck_severity}")
    if dict(sorted(cppcheck_ids.items())) != expected_cppcheck_ids:
        raise RuntimeError(f"Ncurses Cppcheck finding inventory changed: {cppcheck_ids}")

    gcc_text = artifacts["gcc-analyzer.log"].read_text(errors="replace")
    gcc_checks = Counter(re.findall(r"\[-W([^]]+)\]", gcc_text))
    expected_gcc = {
        "analyzer-malloc-leak": 8, "analyzer-null-dereference": 2,
        "analyzer-possible-null-dereference": 1,
        "analyzer-use-of-uninitialized-value": 2,
    }
    if dict(sorted(gcc_checks.items())) != expected_gcc:
        raise RuntimeError(f"Ncurses GCC analyzer inventory changed: {gcc_checks}")

    clang_text = artifacts["clang-analyzer-tidy.log"].read_text(errors="replace")
    clang_checks = Counter(re.findall(
        r"\[([A-Za-z][A-Za-z0-9_.-]*-[A-Za-z0-9_.-]+)\]$", clang_text, re.MULTILINE
    ))
    expected_clang = {
        "bugprone-assignment-in-if-condition": 265,
        "bugprone-branch-clone": 31, "bugprone-casting-through-void": 25,
        "bugprone-easily-swappable-parameters": 70,
        "bugprone-implicit-widening-of-multiplication-result": 30,
        "bugprone-inc-dec-in-conditions": 18, "bugprone-integer-division": 1,
        "bugprone-macro-parentheses": 115, "bugprone-misplaced-widening-cast": 3,
        "bugprone-multi-level-implicit-pointer-conversion": 36,
        "bugprone-narrowing-conversions": 7, "bugprone-reserved-identifier": 37,
        "bugprone-signed-char-misuse": 36, "bugprone-suspicious-include": 2,
        "bugprone-suspicious-memory-comparison": 2,
        "bugprone-suspicious-realloc-usage": 1,
        "bugprone-suspicious-semicolon": 1,
        "bugprone-suspicious-string-compare": 16,
        "bugprone-switch-missing-default-case": 37,
        "bugprone-unsafe-functions": 1,
        "clang-analyzer-security.insecureAPI.DeprecatedOrUnsafeBufferHandling": 335,
        "clang-analyzer-security.insecureAPI.strcpy": 73,
        "clang-diagnostic-unused-command-line-argument": 264,
        "performance-no-int-to-ptr": 332,
    }
    if dict(sorted(clang_checks.items())) != expected_clang:
        raise RuntimeError(f"Ncurses Clang analyzer inventory changed: {clang_checks}")

    flawfinder_text = artifacts["flawfinder.log"].read_text(errors="replace")
    flawfinder_hits = re.search(r"^Hits = (\d+)$", flawfinder_text, re.MULTILINE)
    flawfinder_lines = re.search(r"^Lines analyzed = (\d+) ", flawfinder_text, re.MULTILINE)
    if (not flawfinder_hits or not flawfinder_lines
            or (int(flawfinder_hits[1]), int(flawfinder_lines[1])) != (520, 82898)):
        raise RuntimeError("Ncurses Flawfinder inventory changed")

    sparse_text = artifacts["sparse.log"].read_text(errors="replace")
    sparse_errors = len(re.findall(r" error: ", sparse_text))
    sparse_warnings = len(re.findall(r" warning: ", sparse_text))
    statuses = {
        tool: int(artifacts[f"{tool}.status"].read_text().strip())
        for tool in ("gcc-analyzer", "clang-analyzer-tidy", "flawfinder", "sparse")
    }
    if sparse_errors != 0 or sparse_warnings != 34 or any(statuses.values()):
        raise RuntimeError(
            f"Ncurses analyzer status changed: sparse=({sparse_errors}, {sparse_warnings}), {statuses}"
        )

    oracle = json.loads((repository / "evidence/ncurses-6.6-oracle.json").read_text())
    if oracle["inventory"]["production_source_count"] != 264:
        raise RuntimeError("Ncurses oracle production closure changed")
    analyzer_checks = {
        name: count for name, count in sorted(clang_checks.items())
        if name.startswith("clang-analyzer-")
    }
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-22",
        "release": "6.6",
        "status": "complete production audit; deterministic normalization next",
        "scope": {
            "compile_actions": len(commands), "unique_sources": len(sources),
            "c_sources": len(sources),
            "public_names": oracle["inventory"]["public_names"],
            "shared_static_duplicate_actions_deduplicated": True,
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
            },
        },
        "review": {
            "demonstrated_canonical_defects": 1,
            "canonical_source_changes": 0,
            "demonstrated_defects": [{
                "source": "ncurses/tinfo/read_entry.c",
                "line": 92,
                "kind": "signed left-shift undefined behavior",
                "evidence": "UBSan while canonical tic installs the terminfo database",
                "normalization": "assemble the four input bytes through unsigned arithmetic without changing decoded values",
            }],
            "required_normalization": [
                "Remove the sanitizer-confirmed signed shift while preserving compiled terminfo bytes.",
                "Export the ten native utility entrypoints while retaining standalone wrappers.",
                "Keep the complete 264-source configured closure; do not replace library support with translation holes.",
                "Make only translator-demonstrated ownership, width, macro, and generated-code constraints explicit.",
            ],
            "notes": [
                "Cppcheck's eight double-free paths lose ret_error's branch invariant: each free is followed by return or the noreturn ExitTerminfo path.",
                "GCC's write_entry uninitialized report loses the six LITTLE_ENDIAN macro writes that initialize all 12 header bytes before fake_write.",
                "GCC's soft-label null reports lose _nc_slk_initialize's screen and allocation invariants; the GCC/Clang differentials, sanitizer oracle, and public Valgrind paths do not corroborate a defect.",
                "GCC's tabs skip_list report loses the argv parser invariant that the helper receives a nonnull pointer inside the current argument.",
                "GCC allocation reports are duplicated across shared/static models and describe cached library state or process-exit argv storage; public version paths have no direct or indirect Valgrind loss.",
                "Clang's named analyzer findings are insecure-API portability inventory; it reports no core path-sensitive null, lifetime, or uninitialized defect.",
                "Sparse's repeated initializer warnings describe the selected terminal-driver dispatch table across static/shared models; it has no parser error.",
            ],
        },
        "artifacts": {name: sha256(path) for name, path in artifacts.items()},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "blocking": 1, "clang_analyzer": sum(analyzer_checks.values()),
        "cppcheck": sum(cppcheck_severity.values()),
        "flawfinder": int(flawfinder_hits[1]), "gcc": sum(gcc_checks.values()),
        "sparse_parser_errors": sparse_errors,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
