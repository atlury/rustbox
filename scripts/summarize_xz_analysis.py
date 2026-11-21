#!/usr/bin/env python3
"""Summarize XZ Utils 5.8.4's production-only static analysis."""

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
    analysis = repository / "work/analysis/xz-5.8.4/analyzers"
    names = (
        "compile_commands.json", "sources.list", "cppcheck.log",
        "gcc-analyzer-configure.log", "gcc-analyzer.log",
        "clang-analyzer-tidy.log", "flawfinder.log", "sparse.log",
        "sparse.status",
    )
    artifacts = {name: analysis / name for name in names}
    for path in artifacts.values():
        if not path.is_file():
            raise RuntimeError(f"missing XZ analyzer artifact: {path}")

    commands = json.loads(artifacts["compile_commands.json"].read_text())
    sources = [line for line in artifacts["sources.list"].read_text().splitlines() if line]
    if len(commands) != 113 or len(sources) != 101 or len(set(sources)) != 101:
        raise RuntimeError("XZ analyzer production closure changed")

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
        "autoVariables": 3, "constParameterPointer": 3,
        "constVariablePointer": 1, "duplicateCondition": 2,
        "duplicateExpressionTernary": 1, "uninitvar": 1, "zerodiv": 1,
    }
    if dict(sorted(cppcheck_ids.items())) != expected_cppcheck:
        raise RuntimeError(f"XZ Cppcheck findings changed: {cppcheck_ids}")

    gcc_text = artifacts["gcc-analyzer.log"].read_text(errors="replace")
    gcc_checks = Counter(re.findall(r"\[-W([^]]+)\]", gcc_text))
    expected_gcc = {"analyzer-fd-leak": 1, "analyzer-null-dereference": 2}
    if dict(sorted(gcc_checks.items())) != expected_gcc:
        raise RuntimeError(f"XZ GCC analyzer findings changed: {gcc_checks}")

    clang_text = artifacts["clang-analyzer-tidy.log"].read_text(errors="replace")
    clang_checks = Counter(re.findall(
        r"\[([A-Za-z][A-Za-z0-9_.-]*-[A-Za-z0-9_.-]+)\]$", clang_text, re.MULTILINE
    ))
    expected_clang = {
        "bugprone-branch-clone": 1,
        "bugprone-easily-swappable-parameters": 65,
        "bugprone-implicit-widening-of-multiplication-result": 16,
        "bugprone-inc-dec-in-conditions": 1,
        "bugprone-macro-parentheses": 58,
        "bugprone-multi-level-implicit-pointer-conversion": 2,
        "bugprone-narrowing-conversions": 3,
        "bugprone-switch-missing-default-case": 5,
        "clang-analyzer-core.BitwiseShift": 1,
        "clang-analyzer-core.NullDereference": 2,
        "clang-analyzer-core.StackAddressEscape": 2,
        "clang-analyzer-core.UndefinedBinaryOperatorResult": 1,
        "clang-analyzer-security.insecureAPI.DeprecatedOrUnsafeBufferHandling": 96,
        "clang-analyzer-valist.Uninitialized": 1,
    }
    if dict(sorted(clang_checks.items())) != expected_clang:
        raise RuntimeError(f"XZ Clang findings changed: {clang_checks}")

    flawfinder_text = artifacts["flawfinder.log"].read_text(errors="replace")
    flawfinder_hits = re.search(r"^Hits = (\d+)$", flawfinder_text, re.MULTILINE)
    flawfinder_lines = re.search(r"^Lines analyzed = (\d+) ", flawfinder_text, re.MULTILINE)
    if (not flawfinder_hits or not flawfinder_lines
            or int(flawfinder_hits[1]) != 110 or int(flawfinder_lines[1]) != 34216):
        raise RuntimeError("XZ Flawfinder summary changed")

    sparse_text = artifacts["sparse.log"].read_text(errors="replace")
    sparse_errors = len(re.findall(r" error: ", sparse_text))
    sparse_warnings = len(re.findall(r" warning: ", sparse_text))
    sparse_status = int(artifacts["sparse.status"].read_text().strip())
    if (sparse_errors, sparse_warnings, sparse_status) != (106, 313, 0):
        raise RuntimeError("XZ Sparse compatibility inventory changed")

    oracle = json.loads((repository / "evidence/xz-5.8.4-oracle.json").read_text())
    if oracle["inventory"]["production_source_count"] != 101:
        raise RuntimeError("XZ oracle production closure changed")

    analyzer_checks = {name: count for name, count in sorted(clang_checks.items())
                       if name.startswith("clang-analyzer-")}
    evidence = {
        "schema": 1, "recorded_at": "2026-11-22", "release": "5.8.4",
        "status": "complete production audit; deterministic normalization pending",
        "scope": {
            "compile_actions": len(commands), "unique_sources": len(sources),
            "public_names": oracle["inventory"]["public_names"],
            "tests_examples_and_nonselected_sources_excluded": True,
        },
        "tools": {
            "cppcheck": {"findings_by_severity": dict(sorted(cppcheck_severity.items())),
                         "findings_by_id": dict(sorted(cppcheck_ids.items()))},
            "gcc_fanalyzer": {"warnings": sum(gcc_checks.values()),
                              "findings_by_check": dict(sorted(gcc_checks.items()))},
            "clang_analyzer_tidy": {
                "analyzer_findings_by_check": analyzer_checks,
                "all_findings_by_check": dict(sorted(clang_checks.items())),
            },
            "flawfinder": {"hits_at_level_1_or_higher": int(flawfinder_hits[1]),
                           "lines_analyzed": int(flawfinder_lines[1])},
            "sparse": {
                "warnings": sparse_warnings, "parser_errors": sparse_errors,
                "exit_status": sparse_status,
                "limitation": "Sparse cannot model GCC x86 CLMUL intrinsics or __builtin_assume_aligned in this configured closure; the portable translation configuration disables CLMUL and is independently compared",
            },
        },
        "review": {
            "demonstrated_canonical_defects": 0,
            "canonical_source_changes": 0,
            "required_normalization": [
                "Export the four physical command entrypoints while retaining standalone wrappers.",
                "Disable the optional CLMUL CRC optimization only in the translation configuration; retain the same CRC behavior through canonical portable C.",
            ],
            "notes": [
                "Cppcheck's xzdec stack-buffer reports confuse lzma_stream's borrowed next_in/next_out pointers with escaped ownership; both buffers remain live for the whole decoding loop.",
                "Cppcheck's division report follows the multiplier==0 path beyond message_fatal(), which is declared noreturn.",
                "GCC and Clang index-tree null reports ignore assertions and invariants established by successful tree lookup; the public tests, sanitizers, and malformed-input corpus exercise those paths without error.",
                "GCC's file-descriptor report is the intentional repair of missing standard descriptors: when open returns exactly descriptor 0, 1, or 2, ownership transfers to the process standard stream until exit.",
                "Clang's x86 shift report cannot reach i==0 because MASK_TO_BIT_NUMBER is indexed only after prev_mask is nonzero; the portable C filter is still retained and differentially tested.",
                "The va_list report ignores the local va_start before vfprintf and va_end after it.",
                "Remaining findings are pointer, macro, conversion, and C buffer-API inventory rather than demonstrated behavioral defects.",
            ],
        },
        "artifacts": {name: sha256(path) for name, path in artifacts.items()},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"blocking": 0, "clang_analyzer": sum(analyzer_checks.values()),
                      "cppcheck": sum(cppcheck_severity.values()),
                      "flawfinder": int(flawfinder_hits[1]),
                      "gcc": sum(gcc_checks.values()),
                      "sparse_parser_errors": sparse_errors}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
