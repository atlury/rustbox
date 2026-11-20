#!/usr/bin/env python3
"""Summarize GNU patch 2.8 production-only static analysis."""

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
    analysis = repository / "work/analysis/patch-2.8/analyzers"
    names = (
        "compile_commands.json", "sources.list", "cppcheck.log",
        "gcc-analyzer-setup.log", "gcc-analyzer.log",
        "clang-analyzer-tidy.log", "flawfinder.log", "sparse.log",
        "sparse.status",
    )
    artifacts = {name: analysis / name for name in names}
    for path in artifacts.values():
        if not path.is_file():
            raise RuntimeError(f"missing GNU patch analyzer artifact: {path}")

    commands = json.loads(artifacts["compile_commands.json"].read_text())
    sources = [line for line in artifacts["sources.list"].read_text().splitlines() if line]
    if len(commands) != 67 or len(sources) != 67 or len(set(sources)) != 67:
        raise RuntimeError("GNU patch analyzer production closure changed")

    cppcheck_text = artifacts["cppcheck.log"].read_text(errors="replace")
    cppcheck_severity = Counter(re.findall(
        r"^(?:/rustbox-patch/source/)?[^:\n]+\.c:\d+:\d+: "
        r"(error|warning|style|performance|portability|information):",
        cppcheck_text, re.MULTILINE,
    ))
    cppcheck_ids = Counter(re.findall(
        r"^(?:/rustbox-patch/source/)?[^:\n]+\.c:\d+:\d+: "
        r"(?:error|warning|style|performance|portability|information): ([A-Za-z0-9_]+):",
        cppcheck_text, re.MULTILINE,
    ))
    expected_cppcheck = {
        "badBitmaskCheck": 2, "clarifyCalculation": 1, "clarifyCondition": 2,
        "constParameterPointer": 4, "constVariablePointer": 8,
        "identicalConditionAfterEarlyExit": 2, "knownConditionTrueFalse": 3,
        "legacyUninitvar": 1, "nullPointerRedundantCheck": 2,
        "preprocessorErrorDirective": 2, "redundantContinue": 5,
        "redundantInitialization": 1, "unreadVariable": 4,
        "unusedStructMember": 2, "uselessAssignmentPtrArg": 1,
        "variableScope": 8,
    }
    if dict(sorted(cppcheck_ids.items())) != expected_cppcheck:
        raise RuntimeError(f"GNU patch Cppcheck findings changed: {cppcheck_ids}")

    gcc_text = artifacts["gcc-analyzer.log"].read_text(errors="replace")
    gcc_checks = Counter(re.findall(r"\[-W([^]]+)\]", gcc_text))
    expected_gcc = {
        "analyzer-fd-leak": 3,
        "analyzer-malloc-leak": 11,
        "analyzer-use-of-uninitialized-value": 2,
        "sign-compare": 3,
    }
    if dict(sorted(gcc_checks.items())) != expected_gcc:
        raise RuntimeError(f"GNU patch GCC analyzer findings changed: {gcc_checks}")

    clang_text = artifacts["clang-analyzer-tidy.log"].read_text(errors="replace")
    clang_checks = Counter(re.findall(r"\[([A-Za-z][A-Za-z0-9_.-]*-[A-Za-z0-9_.-]+)\]$", clang_text, re.MULTILINE))
    clang_analyzer = {
        name: count for name, count in sorted(clang_checks.items())
        if name.startswith("clang-analyzer-")
    }
    expected_clang_analyzer = {
        "clang-analyzer-core.NonNullParamChecker": 5,
        "clang-analyzer-core.uninitialized.Branch": 3,
        "clang-analyzer-deadcode.DeadStores": 2,
        "clang-analyzer-optin.core.EnumCastOutOfRange": 4,
        "clang-analyzer-security.insecureAPI.DeprecatedOrUnsafeBufferHandling": 60,
        "clang-analyzer-security.insecureAPI.strcpy": 14,
        "clang-analyzer-unix.Malloc": 3,
    }
    if clang_analyzer != expected_clang_analyzer:
        raise RuntimeError(f"GNU patch Clang analyzer findings changed: {clang_analyzer}")

    flawfinder_text = artifacts["flawfinder.log"].read_text(errors="replace")
    flawfinder_hits = re.search(r"^Hits = (\d+)$", flawfinder_text, re.MULTILINE)
    flawfinder_lines = re.search(r"^Lines analyzed = (\d+) ", flawfinder_text, re.MULTILINE)
    if not flawfinder_hits or not flawfinder_lines or int(flawfinder_hits.group(1)) != 257:
        raise RuntimeError("GNU patch Flawfinder summary changed")

    sparse_text = artifacts["sparse.log"].read_text(errors="replace")
    sparse_errors = len(re.findall(r" error: ", sparse_text))
    sparse_warnings = len(re.findall(r" warning: ", sparse_text))
    if sparse_errors != 135 or sparse_warnings != 141:
        raise RuntimeError(f"GNU patch Sparse output changed: {sparse_errors}/{sparse_warnings}")

    oracle = json.loads((repository / "evidence/patch-2.8-oracle.json").read_text())
    if oracle["scope"]["unique_production_sources"] != 67:
        raise RuntimeError("GNU patch oracle production closure changed")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-20",
        "release": "2.8",
        "scope": {
            "compile_actions": len(commands),
            "unique_sources": len(sources),
            "targets": ["patch"],
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
            "sparse": {
                "warnings": sparse_warnings,
                "parser_errors": sparse_errors,
                "parser_limited_sources": [
                    "lib/malloc/scratch_buffer_grow.c",
                    "lib/malloc/scratch_buffer_grow_preserve.c",
                    "lib/malloc/scratch_buffer_set_array_size.c",
                    "src/merge.c",
                    "src/pch.c",
                ],
            },
        },
        "review": {
            "blocking_findings": 0,
            "canonical_source_changes": 0,
            "notes": [
                "Cppcheck's legacyUninitvar in pch.c is a short-circuit false positive: s is assigned whenever invalid_line is false, and invalid_line prevents dereference otherwise.",
                "Cppcheck's preprocessor errors are platform-selection guards analyzed without configure's per-file conditions; both configured compiler builds select valid branches.",
                "GCC's xmalloc reports treat allocation-returning helper results as leaks at function return; ownership is intentionally transferred to callers.",
                "GCC and Clang report the same time_rz old_tz ownership path, but the gnulib local_tz sentinel and revert_tz protocol retain or release it by design; full ASan/LSan and Valgrind gates report no definite, indirect, or possible leak.",
                "The three stdopen descriptor reports do not model its deliberate movement of descriptors into standard slots; canonical tests and Valgrind exercise the configured implementation without an open-descriptor failure.",
                "GCC's merge.c uninitialized report contradicts the explicit idx_t old = 1 initializer; Clang's pch.c array reports lose the invariant that only populated name slots are read after their companion arrays are initialized.",
                "Clang's NonNull reports lose global parser invariants for outname and the output stream; upstream and generated differential cases cover those paths under ASan/UBSan.",
                "Clang's EnumCastOutOfRange sites intentionally use enum file_attributes as a bitmask with zero as the empty set.",
                "The remaining Clang-Tidy and Flawfinder results are modernization and lexical-risk inventory for the later pointer-hardening phase, not executable defect proofs.",
                "Sparse parses most of the closure but cannot fully parse gnulib's generated alignas storage or GNU patch's pure-function attribute placement; its parser errors are recorded rather than misreported as program defects.",
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
