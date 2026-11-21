#!/usr/bin/env python3
"""Summarize attr 2.6.0's production-only static analysis."""

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
    analysis = repository / "work/analysis/attr-2.6.0/analyzers"
    names = (
        "compile_commands.json", "sources.list", "cppcheck.log",
        "gcc-analyzer-setup.log", "gcc-analyzer.log",
        "clang-analyzer-tidy.log", "flawfinder.log", "sparse.log", "sparse.status",
    )
    artifacts = {name: analysis / name for name in names}
    for path in artifacts.values():
        if not path.is_file():
            raise RuntimeError(f"missing attr analyzer artifact: {path}")

    commands = json.loads(artifacts["compile_commands.json"].read_text())
    sources = [line for line in artifacts["sources.list"].read_text().splitlines() if line]
    if len(commands) != 21 or len(sources) != 21 or len(set(sources)) != 21:
        raise RuntimeError("attr analyzer production closure changed")

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
        "constParameterPointer": 1,
        "constVariablePointer": 5,
        "internalAstError": 1,
        "invalidPrintfArgType_sint": 1,
        "unreadVariable": 2,
        "variableScope": 3,
    }
    if dict(sorted(cppcheck_ids.items())) != expected_cppcheck:
        raise RuntimeError(f"attr Cppcheck findings changed: {cppcheck_ids}")

    gcc_text = artifacts["gcc-analyzer.log"].read_text(errors="replace")
    gcc_checks = Counter(re.findall(r"\[-W([^]]+)\]", gcc_text))
    if gcc_checks:
        raise RuntimeError(f"attr GCC analyzer findings changed: {gcc_checks}")

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
        "clang-analyzer-core.NullDereference": 1,
        "clang-analyzer-deadcode.DeadStores": 1,
        "clang-analyzer-security.insecureAPI.DeprecatedOrUnsafeBufferHandling": 53,
        "clang-analyzer-security.insecureAPI.strcpy": 7,
        "clang-analyzer-unix.Malloc": 1,
    }
    if clang_analyzer != expected_clang_analyzer:
        raise RuntimeError(f"attr Clang analyzer findings changed: {clang_analyzer}")

    flawfinder_text = artifacts["flawfinder.log"].read_text(errors="replace")
    flawfinder_hits = re.search(r"^Hits = (\d+)$", flawfinder_text, re.MULTILINE)
    flawfinder_lines = re.search(r"^Lines analyzed = (\d+) ", flawfinder_text, re.MULTILINE)
    if (
        not flawfinder_hits or not flawfinder_lines
        or int(flawfinder_hits.group(1)) != 45
        or int(flawfinder_lines.group(1)) != 3702
    ):
        raise RuntimeError("attr Flawfinder summary changed")

    sparse_text = artifacts["sparse.log"].read_text(errors="replace")
    sparse_errors = len(re.findall(r" error: ", sparse_text))
    sparse_warnings = len(re.findall(r" warning: ", sparse_text))
    sparse_status = int(artifacts["sparse.status"].read_text().strip())
    if sparse_errors != 0 or sparse_warnings != 36 or sparse_status != 0:
        raise RuntimeError(
            f"attr Sparse output changed: {sparse_errors}/{sparse_warnings}/{sparse_status}"
        )

    oracle = json.loads((repository / "evidence/attr-2.6.0-oracle.json").read_text())
    if oracle["scope"]["production_source_count"] != 21:
        raise RuntimeError("attr oracle production closure changed")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-21",
        "release": "2.6.0",
        "status": "complete production audit; deterministic normalization pending",
        "scope": {
            "compile_actions": len(commands),
            "unique_sources": len(sources),
            "targets": ["attr", "getfattr", "setfattr", "libattr"],
            "tests_examples_and_nonselected_sources_excluded": True,
        },
        "tools": {
            "cppcheck": {
                "findings_by_severity": dict(sorted(cppcheck_severity.items())),
                "findings_by_id": dict(sorted(cppcheck_ids.items())),
            },
            "gcc_fanalyzer": {
                "warnings": 0,
                "findings_by_check": {},
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
                "exit_status": sparse_status,
            },
        },
        "review": {
            "blocking_findings": 0,
            "canonical_source_changes": 0,
            "notes": [
                "Cppcheck's internal AST error is its parser losing the configured no-NLS do/while macro structure in attr_copy_action; GCC, Clang, Clang's analyzer, and Sparse parse that unit.",
                "setfattr's realloc warning describes losing process-lifetime storage only on allocation failure immediately followed by exit; successful restore mode increments the count and enforces non-null storage before indexing.",
                "The help-path allocation report crosses a switch arm that returns from main immediately after help; no subsequent use occurs.",
                "getfattr can call glibc qsort with a null base only when the element count is zero after regex filtering; the configured Linux ABI accepts this, and a guarded call is retained as a deterministic normalization candidate.",
                "The dead dirfd store is cleanup bookkeeping after close and has no later read.",
                "The printf signedness diagnostic, implicit integer conversions, and explicit pointer casts are retained as deterministic normalization candidates.",
                "Remaining Tidy, Flawfinder, and Sparse output is API-hardening, public libattr linkage, macro, and pointer inventory rather than a demonstrated functional defect.",
                "Both ordinary upstream components, 22 cross-compiler cases, ASan/UBSan, and Valgrind exercise attribute mutation, query, traversal, encoding, restore, and error paths.",
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
        "gcc": 0,
        "sparse_warnings": sparse_warnings,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
