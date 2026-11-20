#!/usr/bin/env python3
"""Summarize GNU sed 4.10 production-only static analysis."""

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
    analysis = repository / "work/analysis/sed-4.10/analyzers"
    names = (
        "compile_commands.json", "sources.list", "cppcheck.log",
        "gcc-analyzer-setup.log", "gcc-analyzer.log",
        "clang-analyzer-tidy.log", "flawfinder.log", "sparse.log", "sparse.status",
    )
    artifacts = {name: analysis / name for name in names}
    for path in artifacts.values():
        if not path.is_file():
            raise RuntimeError(f"missing GNU sed analyzer artifact: {path}")

    commands = json.loads(artifacts["compile_commands.json"].read_text())
    sources = [line for line in artifacts["sources.list"].read_text().splitlines() if line]
    if len(commands) != 85 or len(sources) != 85 or len(set(sources)) != 85:
        raise RuntimeError("GNU sed analyzer production closure changed")

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
        "constParameterPointer": 12, "constVariablePointer": 9,
        "internalAstError": 1, "knownConditionTrueFalse": 9,
        "preprocessorErrorDirective": 2, "redundantContinue": 2,
        "redundantInitialization": 1, "shadowFunction": 1,
        "syntaxError": 1, "unsignedLessThanZero": 1,
        "unusedStructMember": 3, "variableScope": 7,
    }
    if dict(sorted(cppcheck_ids.items())) != expected_cppcheck:
        raise RuntimeError(f"GNU sed Cppcheck findings changed: {cppcheck_ids}")

    gcc_text = artifacts["gcc-analyzer.log"].read_text(errors="replace")
    gcc_checks = Counter(re.findall(r"\[-W([^]]+)\]", gcc_text))
    expected_gcc = {
        "analyzer-malloc-leak": 7, "sign-compare": 10,
        "unused-value": 7, "unused-variable": 2,
    }
    if dict(sorted(gcc_checks.items())) != expected_gcc:
        raise RuntimeError(f"GNU sed GCC analyzer findings changed: {gcc_checks}")

    clang_text = artifacts["clang-analyzer-tidy.log"].read_text(errors="replace")
    clang_checks = Counter(re.findall(
        r"\[([A-Za-z][A-Za-z0-9_.-]*-[A-Za-z0-9_.-]+)\]$", clang_text, re.MULTILINE
    ))
    clang_analyzer = {
        name: count for name, count in sorted(clang_checks.items())
        if name.startswith("clang-analyzer-")
    }
    expected_clang_analyzer = {
        "clang-analyzer-core.CallAndMessage": 1,
        "clang-analyzer-core.NullDereference": 1,
        "clang-analyzer-deadcode.DeadStores": 4,
        "clang-analyzer-security.insecureAPI.DeprecatedOrUnsafeBufferHandling": 181,
        "clang-analyzer-security.insecureAPI.strcpy": 5,
    }
    if clang_analyzer != expected_clang_analyzer:
        raise RuntimeError(f"GNU sed Clang analyzer findings changed: {clang_analyzer}")

    flawfinder_text = artifacts["flawfinder.log"].read_text(errors="replace")
    flawfinder_hits = re.search(r"^Hits = (\d+)$", flawfinder_text, re.MULTILINE)
    flawfinder_lines = re.search(r"^Lines analyzed = (\d+) ", flawfinder_text, re.MULTILINE)
    if not flawfinder_hits or not flawfinder_lines or int(flawfinder_hits.group(1)) != 202:
        raise RuntimeError("GNU sed Flawfinder summary changed")

    sparse_text = artifacts["sparse.log"].read_text(errors="replace")
    sparse_errors = len(re.findall(r" error: ", sparse_text))
    sparse_warnings = len(re.findall(r" warning: ", sparse_text))
    if sparse_errors != 40 or sparse_warnings != 255:
        raise RuntimeError(f"GNU sed Sparse output changed: {sparse_errors}/{sparse_warnings}")

    oracle = json.loads((repository / "evidence/sed-4.10-oracle.json").read_text())
    if oracle["scope"]["unique_production_sources"] != 85:
        raise RuntimeError("GNU sed oracle production closure changed")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-20",
        "release": "4.10",
        "scope": {
            "compile_actions": len(commands),
            "unique_sources": len(sources),
            "targets": ["sed"],
            "tests_and_examples_excluded": True,
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
            "sparse": {"warnings": sparse_warnings, "parser_errors": sparse_errors},
        },
        "review": {
            "blocking_findings": 0,
            "canonical_source_changes": 0,
            "notes": [
                "Cppcheck cannot parse sed.c's translated NLS expression or dfa.c's dense generated-style condition; both production compilers and the sanitizer suite compile and exercise them.",
                "Cppcheck's preprocessor errors are configure/platform-selection guards analyzed outside their selected branches.",
                "GCC's seven xmalloc-family leaks model allocation-returning helpers as owners at return; ownership is intentionally transferred to each caller.",
                "Clang's execute.c uninitialized ownership report invents a path where in-place cleanup uses stat data despite in-place mode being disabled; open_next_file initializes the stat record on every real in-place path.",
                "Clang's dfa.c null report loses realloc_trans_if_necessary's invariant that d->trans is allocated whenever tralloc is nonzero; the canonical regex suite and sanitizer coverage exercise this loop.",
                "The remaining Clang-Tidy and Flawfinder results are modernization and lexical-risk inventory for the later pointer-hardening phase, not executable defect proofs.",
                "Sparse's parser errors reflect gnulib generated headers, C23 constructs, and attribute syntax outside Sparse's configured grammar; they are recorded rather than treated as program defects.",
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

