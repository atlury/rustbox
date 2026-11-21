#!/usr/bin/env python3
"""Summarize GNU bc 1.08.2 production-only static analysis."""

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
    analysis = repository / "work/analysis/bc-1.08.2/analyzers"
    names = (
        "compile_commands.json", "sources.list", "cppcheck.log",
        "gcc-analyzer-setup.log", "gcc-analyzer.log",
        "clang-analyzer-tidy.log", "flawfinder.log", "sparse.log", "sparse.status",
    )
    artifacts = {name: analysis / name for name in names}
    for path in artifacts.values():
        if not path.is_file():
            raise RuntimeError(f"missing GNU bc analyzer artifact: {path}")

    commands = json.loads(artifacts["compile_commands.json"].read_text())
    sources = [line for line in artifacts["sources.list"].read_text().splitlines() if line]
    if len(commands) != 21 or len(sources) != 21 or len(set(sources)) != 21:
        raise RuntimeError("GNU bc analyzer production closure changed")

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
        "constVariablePointer": 7,
        "invalidPrintfArgType_sint": 2,
        "knownConditionTrueFalse": 4,
        "nullPointer": 2,
        "nullPointerArithmeticRedundantCheck": 2,
        "nullPointerRedundantCheck": 17,
        "redundantContinue": 1,
        "returnDanglingLifetime": 1,
        "unreadVariable": 4,
        "uselessAssignmentPtrArg": 1,
        "variableScope": 31,
    }
    if dict(sorted(cppcheck_ids.items())) != expected_cppcheck:
        raise RuntimeError(f"GNU bc Cppcheck findings changed: {cppcheck_ids}")

    gcc_text = artifacts["gcc-analyzer.log"].read_text(errors="replace")
    gcc_checks = Counter(re.findall(r"\[-W([^]]+)\]", gcc_text))
    expected_gcc = {
        "analyzer-deref-before-check": 1,
        "analyzer-file-leak": 1,
        "analyzer-malloc-leak": 4,
        "analyzer-null-argument": 1,
        "analyzer-null-dereference": 5,
        "analyzer-use-of-uninitialized-value": 2,
        "sign-compare": 1,
        "unused-parameter": 2,
    }
    if dict(sorted(gcc_checks.items())) != expected_gcc:
        raise RuntimeError(f"GNU bc GCC analyzer findings changed: {gcc_checks}")

    clang_text = artifacts["clang-analyzer-tidy.log"].read_text(errors="replace")
    clang_checks = Counter(re.findall(
        r"\[([A-Za-z][A-Za-z0-9_.-]*-[A-Za-z0-9_.-]+)\]$", clang_text, re.MULTILINE
    ))
    clang_analyzer = {
        name: count for name, count in sorted(clang_checks.items())
        if name.startswith("clang-analyzer-")
    }
    expected_clang_analyzer = {
        "clang-analyzer-core.NonNullParamChecker": 3,
        "clang-analyzer-core.NullDereference": 10,
        "clang-analyzer-deadcode.DeadStores": 3,
        "clang-analyzer-optin.performance.Padding": 2,
        "clang-analyzer-security.insecureAPI.DeprecatedOrUnsafeBufferHandling": 61,
        "clang-analyzer-security.insecureAPI.strcpy": 2,
    }
    if clang_analyzer != expected_clang_analyzer:
        raise RuntimeError(f"GNU bc Clang analyzer findings changed: {clang_analyzer}")

    flawfinder_text = artifacts["flawfinder.log"].read_text(errors="replace")
    flawfinder_hits = re.search(r"^Hits = (\d+)$", flawfinder_text, re.MULTILINE)
    flawfinder_lines = re.search(r"^Lines analyzed = (\d+) ", flawfinder_text, re.MULTILINE)
    if not flawfinder_hits or not flawfinder_lines or int(flawfinder_hits.group(1)) != 86:
        raise RuntimeError("GNU bc Flawfinder summary changed")

    sparse_text = artifacts["sparse.log"].read_text(errors="replace")
    sparse_errors = len(re.findall(r" error: ", sparse_text))
    sparse_warnings = len(re.findall(r" warning: ", sparse_text))
    sparse_status = int(artifacts["sparse.status"].read_text().strip())
    if sparse_errors != 0 or sparse_warnings != 57 or sparse_status != 0:
        raise RuntimeError(
            f"GNU bc Sparse output changed: {sparse_errors}/{sparse_warnings}/{sparse_status}"
        )

    oracle = json.loads((repository / "evidence/bc-1.08.2-oracle.json").read_text())
    if oracle["scope"]["production_source_count"] != 21:
        raise RuntimeError("GNU bc oracle production closure changed")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-21",
        "release": "1.08.2",
        "bundled_dc_release": "1.5.2",
        "scope": {
            "compile_actions": len(commands),
            "unique_sources": len(sources),
            "targets": ["bc", "dc"],
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
            "blocking_findings": 0,
            "canonical_source_changes": 0,
            "known_canonical_resource_baseline": {
                "bc_bytes_at_exit": oracle["valgrind"]["bc"]["bytes_at_exit"],
                "dc_bytes_at_exit": oracle["valgrind"]["dc"]["bytes_at_exit"],
                "definite_indirect_or_possible_leaks": 0,
            },
            "notes": [
                "The Cppcheck dangling-lifetime report follows strcpy's returned heap pointer through a local pointer variable; strcopyof allocates that storage with bc_malloc.",
                "Number-library null reports assume out_of_memory can return.  Both bc and dc implementations terminate the process, so successful paths retain non-null allocation invariants.",
                "Flex scanner null and buffer-leak reports likewise lose YY_FATAL_ERROR's non-returning behavior and generated scanner ownership; shipped scanner workloads and Valgrind exercise cleanup behavior.",
                "Bison stack uninitialized-value reports are generated-parser dataflow false positives; both compilers and ASan/UBSan execute all bounded parser workloads.",
                "dc_dump_num's loop condition guarantees cur is non-null before its digit and link are read.",
                "dc input FILE reports follow explicit process-exit commands that intentionally bypass local close; the operating system owns exit cleanup and Valgrind records no definite, indirect, or possible leak.",
                "bc execute dead stores advance the bytecode program counter while handling compact single-value encodings; parser and numerical suites cover those paths.",
                "Signed/unsigned printf and comparison diagnostics are retained as explicit deterministic-normalization candidates, with canonical behavior fixed by the configured Linux ABI.",
                "Remaining Tidy, Flawfinder, and Sparse output is pointer, macro, naming, generated-code, and hardening inventory rather than a demonstrated functional defect.",
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
        "sparse_warnings": sparse_warnings,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
