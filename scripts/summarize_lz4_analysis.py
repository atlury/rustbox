#!/usr/bin/env python3
"""Summarize LZ4 1.11.1's production-only static analysis."""

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
    analysis = repository / "work/analysis/lz4-1.11.1/analyzers"
    names = (
        "compile_commands.json", "sources.list", "cppcheck.log",
        "gcc-analyzer.log", "clang-analyzer-tidy.log", "flawfinder.log",
        "sparse.log", "sparse.status",
    )
    artifacts = {name: analysis / name for name in names}
    for path in artifacts.values():
        if not path.is_file():
            raise RuntimeError(f"missing LZ4 analyzer artifact: {path}")

    commands = json.loads(artifacts["compile_commands.json"].read_text())
    sources = [line for line in artifacts["sources.list"].read_text().splitlines() if line]
    if len(commands) != 24 or len(sources) != 12 or len(set(sources)) != 12:
        raise RuntimeError("LZ4 analyzer production closure changed")

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
        "constParameterPointer": 4,
        "constVariablePointer": 15,
        "invalidPrintfArgType_uint": 1,
        "knownConditionTrueFalse": 7,
        "unsignedLessThanZero": 1,
        "unusedStructMember": 4,
    }
    if dict(sorted(cppcheck_ids.items())) != expected_cppcheck:
        raise RuntimeError(f"LZ4 Cppcheck findings changed: {cppcheck_ids}")

    gcc_text = artifacts["gcc-analyzer.log"].read_text(errors="replace")
    gcc_checks = Counter(re.findall(r"\[-W([^]]+)\]", gcc_text))
    expected_gcc = {
        "analyzer-double-free": 2,
        "analyzer-malloc-leak": 6,
        "analyzer-null-argument": 4,
        "analyzer-null-dereference": 2,
        "analyzer-out-of-bounds": 26,
    }
    if dict(sorted(gcc_checks.items())) != expected_gcc:
        raise RuntimeError(f"LZ4 GCC analyzer findings changed: {gcc_checks}")

    clang_text = artifacts["clang-analyzer-tidy.log"].read_text(errors="replace")
    clang_checks = Counter(re.findall(
        r"\[([A-Za-z][A-Za-z0-9_.-]*-[A-Za-z0-9_.-]+)\]$", clang_text, re.MULTILINE
    ))
    expected_clang = {
        "bugprone-branch-clone": 6,
        "bugprone-casting-through-void": 1,
        "bugprone-easily-swappable-parameters": 65,
        "bugprone-implicit-widening-of-multiplication-result": 102,
        "bugprone-macro-parentheses": 27,
        "bugprone-multi-level-implicit-pointer-conversion": 3,
        "bugprone-narrowing-conversions": 4,
        "bugprone-reserved-identifier": 1,
        "bugprone-suspicious-include": 1,
        "bugprone-suspicious-string-compare": 1,
        "bugprone-switch-missing-default-case": 2,
        "clang-analyzer-core.NonNullParamChecker": 2,
        "clang-analyzer-optin.core.EnumCastOutOfRange": 1,
        "clang-analyzer-optin.portability.UnixAPI": 1,
        "clang-analyzer-security.insecureAPI.DeprecatedOrUnsafeBufferHandling": 566,
        "clang-analyzer-security.insecureAPI.strcpy": 2,
        "clang-analyzer-unix.cstring.NullArg": 4,
        "performance-no-int-to-ptr": 2,
    }
    if dict(sorted(clang_checks.items())) != expected_clang:
        raise RuntimeError(f"LZ4 Clang findings changed: {clang_checks}")
    clang_analyzer = {
        name: count for name, count in sorted(clang_checks.items())
        if name.startswith("clang-analyzer-")
    }

    flawfinder_text = artifacts["flawfinder.log"].read_text(errors="replace")
    flawfinder_hits = re.search(r"^Hits = (\d+)$", flawfinder_text, re.MULTILINE)
    flawfinder_lines = re.search(r"^Lines analyzed = (\d+) ", flawfinder_text, re.MULTILINE)
    if (
        not flawfinder_hits or not flawfinder_lines
        or int(flawfinder_hits.group(1)) != 114
        or int(flawfinder_lines.group(1)) != 16809
    ):
        raise RuntimeError("LZ4 Flawfinder summary changed")

    sparse_text = artifacts["sparse.log"].read_text(errors="replace")
    sparse_errors = len(re.findall(r" error: ", sparse_text))
    sparse_warnings = len(re.findall(r" warning: ", sparse_text))
    sparse_status = int(artifacts["sparse.status"].read_text().strip())
    if sparse_errors != 0 or sparse_warnings != 12 or sparse_status != 0:
        raise RuntimeError(
            f"LZ4 Sparse output changed: {sparse_errors}/{sparse_warnings}/{sparse_status}"
        )

    oracle = json.loads((repository / "evidence/lz4-1.11.1-oracle.json").read_text())
    if oracle["inventory"]["production_source_count"] != 12:
        raise RuntimeError("LZ4 oracle production closure changed")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-21",
        "release": "1.11.1",
        "status": "complete production audit; deterministic normalization pending",
        "scope": {
            "compile_actions": len(commands),
            "unique_sources": len(sources),
            "targets": ["lz4", "lz4c", "lz4cat", "unlz4", "embedded liblz4", "embedded xxhash"],
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
                "Make LZ4_CLEVEL_DEFAULT match the help format's unsigned vararg type; Cppcheck identifies the canonical signed-int/%u mismatch.",
                "Guard the two dictionary memcpy calls whose modeled public API paths permit a null destination with zero length.",
                "Replace the exactly-sized automatic output-name strcpy/strcat pair with one bounded copy sequence before translation.",
            ],
            "notes": [
                "GCC's UTIL_realloc double-free paths are infeasible: successful realloc returns immediately, while failed realloc leaves the original allocation valid for the documented free.",
                "GCC's six decompression-resource leaks stop at the resource constructor return and do not follow the caller to LZ4IO_freeDResources; Valgrind observes all resources freed in compression and decompression.",
                "The LZ4F error-code table reports are analyzer range-model artifacts over negative size_t-encoded error values, not buffer reads selected by production control flow.",
                "The packed unaligned-load null reports require invalid internal match pointers; the portable memcpy implementation will be selected for translation and independently compared.",
                "The enum increment reaches analyzer value 8 only for an invalid requested block-size identifier; supported identifiers stop at LZ4F_max4MB.",
                "The automatic output name allocates strlen(input)+5 bytes for the four-byte .lz4 suffix and terminator, so the reported strcpy/strcat calls are bounded but are normalized for explicitness.",
                "Remaining Tidy, Flawfinder, and Sparse output is macro, conversion, buffer-API, and pointer inventory rather than a demonstrated behavioral defect.",
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
