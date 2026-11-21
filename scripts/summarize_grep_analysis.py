#!/usr/bin/env python3
"""Summarize GNU Grep 3.12 production-only static analysis."""

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
    analysis = repository / "work/analysis/grep-3.12/analyzers"
    names = (
        "compile_commands.json", "sources.list", "cppcheck.log",
        "gcc-analyzer-setup.log", "gcc-analyzer.log",
        "clang-analyzer-tidy.log", "flawfinder.log", "sparse.log", "sparse.status",
    )
    artifacts = {name: analysis / name for name in names}
    for path in artifacts.values():
        if not path.is_file():
            raise RuntimeError(f"missing GNU Grep analyzer artifact: {path}")

    commands = json.loads(artifacts["compile_commands.json"].read_text())
    sources = [line for line in artifacts["sources.list"].read_text().splitlines() if line]
    if len(commands) != 129 or len(sources) != 129 or len(set(sources)) != 129:
        raise RuntimeError("GNU Grep analyzer production closure changed")

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
        "clarifyCalculation": 4, "clarifyCondition": 11,
        "constParameterPointer": 6, "constVariablePointer": 3,
        "duplicateExpressionTernary": 2, "internalAstError": 1,
        "knownConditionTrueFalse": 9, "nullPointerRedundantCheck": 1,
        "preprocessorErrorDirective": 1, "redundantAssignment": 1,
        "redundantContinue": 3, "unsignedLessThanZero": 1,
        "unusedStructMember": 2, "variableScope": 2,
    }
    if dict(sorted(cppcheck_ids.items())) != expected_cppcheck:
        raise RuntimeError(f"GNU Grep Cppcheck findings changed: {cppcheck_ids}")

    gcc_text = artifacts["gcc-analyzer.log"].read_text(errors="replace")
    gcc_checks = Counter(re.findall(r"\[-W([^]]+)\]", gcc_text))
    expected_gcc = {
        "analyzer-malloc-leak": 10,
        "analyzer-null-argument": 1,
        "sign-compare": 4,
        "unused-parameter": 32,
    }
    if dict(sorted(gcc_checks.items())) != expected_gcc:
        raise RuntimeError(f"GNU Grep GCC analyzer findings changed: {gcc_checks}")

    clang_text = artifacts["clang-analyzer-tidy.log"].read_text(errors="replace")
    clang_checks = Counter(re.findall(
        r"\[([A-Za-z][A-Za-z0-9_.-]*-[A-Za-z0-9_.-]+)\]$", clang_text, re.MULTILINE
    ))
    clang_analyzer = {
        name: count for name, count in sorted(clang_checks.items())
        if name.startswith("clang-analyzer-")
    }
    expected_clang_analyzer = {
        "clang-analyzer-core.NonNullParamChecker": 2,
        "clang-analyzer-core.NullDereference": 6,
        "clang-analyzer-deadcode.DeadStores": 3,
        "clang-analyzer-security.insecureAPI.DeprecatedOrUnsafeBufferHandling": 132,
        "clang-analyzer-security.insecureAPI.strcpy": 7,
    }
    if clang_analyzer != expected_clang_analyzer:
        raise RuntimeError(f"GNU Grep Clang analyzer findings changed: {clang_analyzer}")

    flawfinder_text = artifacts["flawfinder.log"].read_text(errors="replace")
    flawfinder_hits = re.search(r"^Hits = (\d+)$", flawfinder_text, re.MULTILINE)
    flawfinder_lines = re.search(r"^Lines analyzed = (\d+) ", flawfinder_text, re.MULTILINE)
    if not flawfinder_hits or not flawfinder_lines or int(flawfinder_hits.group(1)) != 259:
        raise RuntimeError("GNU Grep Flawfinder summary changed")

    sparse_text = artifacts["sparse.log"].read_text(errors="replace")
    sparse_errors = len(re.findall(r" error: ", sparse_text))
    sparse_warnings = len(re.findall(r" warning: ", sparse_text))
    if sparse_errors != 7 or sparse_warnings != 161:
        raise RuntimeError(f"GNU Grep Sparse output changed: {sparse_errors}/{sparse_warnings}")

    oracle = json.loads((repository / "evidence/grep-3.12-oracle.json").read_text())
    if oracle["scope"]["normal_production_sources"] != 129:
        raise RuntimeError("GNU Grep oracle production closure changed")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-21",
        "release": "3.12",
        "scope": {
            "compile_actions": len(commands),
            "unique_sources": len(sources),
            "targets": ["grep", "egrep", "fgrep"],
            "tests_examples_and_nonselected_sources_excluded": True,
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
                "possibly_lost_bytes": oracle["valgrind"]["possibly_lost_bytes"],
                "still_reachable_bytes": oracle["valgrind"]["still_reachable_bytes"],
            },
            "notes": [
                "Cppcheck's chdir-long preprocessor error omits the configured PATH_MAX selection; the production compile database selects the valid branch.",
                "Cppcheck's dfa internal AST error is a parser limitation at a C23 checked-add expression; GCC, Clang, and sanitizer builds compile and exercise it.",
                "GCC's xmalloc-family and searchutils reports stop at allocation-returning functions; ownership is transferred to the caller.  exclude.c transfers its string to a hash table.",
                "GCC's fts directory-stream report does not follow the FTS traversal object's retained ownership; the null cp path also assumes xrealloc can return, although the wrapper exits on allocation failure.",
                "Clang's kwsearch and dfasearch memcpy reports likewise do not model the xmalloc-family as non-returning on allocation failure.",
                "Clang's color-string reports lose initialization invariants: every color slot and the line-color argument are initialized to non-null empty strings before output paths run.",
                "Clang's kwset null reports lose the trie-construction invariant: kwsprep runs only after at least one inserted keyword, and the traversal stack contains constructed trie nodes.",
                "Clang's dfa trans report loses the state-index invariant that selects either the allocated transition table or the separate fails table.",
                "Dead-store findings are deliberate parser/lookahead state updates or expression-local indexing and are covered by upstream DFA/kwset tests.",
                "The dfasearch bitwise/conditional precedence warning is semantically intentional but will be parenthesized during deterministic normalization for translation clarity.",
                "Remaining Tidy and Flawfinder results are portability, buffer-hardening, and pointer-modernization inventory rather than demonstrated defects.",
                "Sparse parser errors arise from configured gnulib attributes and C23 syntax outside its grammar and are recorded rather than suppressed.",
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
