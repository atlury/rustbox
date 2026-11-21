#!/usr/bin/env python3
"""Summarize acl 2.4.0's production-only static analysis."""

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
    analysis = repository / "work/analysis/acl-2.4.0/analyzers"
    names = (
        "compile_commands.json", "sources.list", "cppcheck.log",
        "gcc-analyzer-setup.log", "gcc-analyzer.log",
        "clang-analyzer-tidy.log", "flawfinder.log", "sparse.log", "sparse.status",
    )
    artifacts = {name: analysis / name for name in names}
    for path in artifacts.values():
        if not path.is_file():
            raise RuntimeError(f"missing acl analyzer artifact: {path}")

    commands = json.loads(artifacts["compile_commands.json"].read_text())
    sources = [line for line in artifacts["sources.list"].read_text().splitlines() if line]
    if len(commands) != 137 or len(sources) != 72 or len(set(sources)) != 72:
        raise RuntimeError("acl analyzer production closure changed")

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
        "allocaCalled": 3,
        "constParameterPointer": 2,
        "constVariablePointer": 9,
        "knownConditionTrueFalse": 1,
        "memleakOnRealloc": 1,
        "nullPointer": 2,
        "nullPointerArithmeticRedundantCheck": 2,
        "sizeofDivisionMemfunc": 2,
        "uninitvar": 1,
        "unreadVariable": 2,
        "variableScope": 6,
    }
    if dict(sorted(cppcheck_ids.items())) != expected_cppcheck:
        raise RuntimeError(f"acl Cppcheck findings changed: {cppcheck_ids}")

    gcc_text = artifacts["gcc-analyzer.log"].read_text(errors="replace")
    gcc_checks = Counter(re.findall(r"\[-W([^]]+)\]", gcc_text))
    if dict(gcc_checks) != {"analyzer-malloc-leak": 1}:
        raise RuntimeError(f"acl GCC analyzer findings changed: {gcc_checks}")

    clang_text = artifacts["clang-analyzer-tidy.log"].read_text(errors="replace")
    clang_checks = Counter(re.findall(
        r"\[([A-Za-z][A-Za-z0-9_.-]*-[A-Za-z0-9_.-]+)\]$", clang_text, re.MULTILINE
    ))
    clang_analyzer = {
        name: count for name, count in sorted(clang_checks.items())
        if name.startswith("clang-analyzer-")
    }
    expected_clang_analyzer = {
        "clang-analyzer-core.NonNullParamChecker": 7,
        "clang-analyzer-core.NullDereference": 1,
        "clang-analyzer-core.UndefinedBinaryOperatorResult": 2,
        "clang-analyzer-deadcode.DeadStores": 2,
        "clang-analyzer-optin.core.EnumCastOutOfRange": 1,
        "clang-analyzer-security.insecureAPI.DeprecatedOrUnsafeBufferHandling": 83,
        "clang-analyzer-security.insecureAPI.strcpy": 3,
        "clang-analyzer-unix.Malloc": 3,
    }
    if clang_analyzer != expected_clang_analyzer:
        raise RuntimeError(f"acl Clang analyzer findings changed: {clang_analyzer}")

    flawfinder_text = artifacts["flawfinder.log"].read_text(errors="replace")
    flawfinder_hits = re.search(r"^Hits = (\d+)$", flawfinder_text, re.MULTILINE)
    flawfinder_lines = re.search(r"^Lines analyzed = (\d+) ", flawfinder_text, re.MULTILINE)
    if (
        not flawfinder_hits or not flawfinder_lines
        or int(flawfinder_hits.group(1)) != 48
        or int(flawfinder_lines.group(1)) != 8250
    ):
        raise RuntimeError("acl Flawfinder summary changed")

    sparse_text = artifacts["sparse.log"].read_text(errors="replace")
    sparse_errors = len(re.findall(r" error: ", sparse_text))
    sparse_warnings = len(re.findall(r" warning: ", sparse_text))
    sparse_status = int(artifacts["sparse.status"].read_text().strip())
    if sparse_errors != 0 or sparse_warnings != 37 or sparse_status != 0:
        raise RuntimeError(
            f"acl Sparse output changed: {sparse_errors}/{sparse_warnings}/{sparse_status}"
        )

    oracle = json.loads((repository / "evidence/acl-2.4.0-oracle.json").read_text())
    if oracle["scope"]["production_source_count"] != 72:
        raise RuntimeError("acl oracle production closure changed")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-21",
        "release": "2.4.0",
        "status": "complete production audit; deterministic normalization pending",
        "scope": {
            "compile_actions": len(commands),
            "unique_sources": len(sources),
            "targets": ["chacl", "getfacl", "setfacl", "libacl"],
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
                "exit_status": sparse_status,
            },
        },
        "review": {
            "blocking_findings": 1,
            "canonical_source_changes": 0,
            "required_normalization": [
                "Move both external-to-internal object pointer subtractions after their null checks; UBSan demonstrates the __libobj instance and Cppcheck finds the matching acl_free instance.",
                "Retain restore_args ownership across realloc failure so the original allocation remains available to cleanup.",
            ],
            "notes": [
                "The restore dirname allocation is freed at the shared resume label; GCC and Clang reports do not model that goto cleanup precisely.",
                "The tabular getfacl ACL/name lists advance together, making reported tag and list null paths infeasible under the internal invariant exercised by upstream tests.",
                "read_acl_comments and read_acl_seq are internal APIs whose callers provide line and source-offset storage; the analyzer explores unsupported null output arguments.",
                "The zero-valued walk flag is a valid empty bitmask even though Clang models the enum as excluding zero.",
                "Remaining Tidy, Flawfinder, and Sparse output is API-hardening, macro, conversion, and pointer inventory rather than a demonstrated behavioral defect.",
            ],
        },
        "artifacts": {name: sha256(path) for name, path in artifacts.items()},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "blocking": 1,
        "clang_analyzer": sum(clang_analyzer.values()),
        "cppcheck": sum(cppcheck_severity.values()),
        "flawfinder": int(flawfinder_hits.group(1)),
        "gcc": sum(gcc_checks.values()),
        "sparse_warnings": sparse_warnings,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
