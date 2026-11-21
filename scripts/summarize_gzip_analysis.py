#!/usr/bin/env python3
"""Summarize GNU Gzip 1.14's production-only static-analysis baseline."""

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
    analysis = repository / "work/analysis/gzip-1.14/analyzers"
    names = (
        "compile_commands.json", "sources.list", "cppcheck.log",
        "gcc-analyzer-setup.log", "gcc-analyzer.log",
        "clang-analyzer-tidy.log", "flawfinder.log", "sparse.log",
        "sparse.status",
    )
    artifacts = {name: analysis / name for name in names}
    for path in artifacts.values():
        if not path.is_file():
            raise RuntimeError(f"missing GNU Gzip analyzer artifact: {path}")

    commands = json.loads(artifacts["compile_commands.json"].read_text())
    sources = [line for line in artifacts["sources.list"].read_text().splitlines() if line]
    if len(commands) != 69 or len(sources) != 69 or len(set(sources)) != 69:
        raise RuntimeError("GNU Gzip analyzer production closure changed")

    cppcheck_text = artifacts["cppcheck.log"].read_text(errors="replace")
    cppcheck_pairs = re.findall(
        r"\.c:\d+:\d+: (error|warning|style|performance|portability|information): "
        r"([A-Za-z0-9_]+):",
        cppcheck_text,
    )
    cppcheck_severity = Counter(severity for severity, _ in cppcheck_pairs)
    cppcheck_ids = Counter(identifier for _, identifier in cppcheck_pairs)
    expected_cppcheck = {
        "allocaCalled": 1,
        "arrayIndexOutOfBoundsCond": 4,
        "constParameterPointer": 6,
        "constVariablePointer": 4,
        "internalAstError": 1,
        "knownConditionTrueFalse": 1,
        "nullPointerRedundantCheck": 3,
        "preprocessorErrorDirective": 3,
        "redundantContinue": 3,
        "redundantInitialization": 3,
        "shadowVariable": 4,
        "truncLongCastAssignment": 1,
        "unreadVariable": 9,
        "unusedStructMember": 3,
        "variableScope": 23,
    }
    if dict(sorted(cppcheck_ids.items())) != expected_cppcheck:
        raise RuntimeError(f"GNU Gzip Cppcheck findings changed: {cppcheck_ids}")

    gcc_text = artifacts["gcc-analyzer.log"].read_text(errors="replace")
    gcc_checks = Counter(re.findall(r"\[-W([^]]+)\]", gcc_text))
    expected_gcc = {
        "analyzer-malloc-leak": 7,
        "analyzer-null-argument": 1,
        "analyzer-use-of-uninitialized-value": 2,
        "sign-compare": 3,
        "unused-parameter": 1,
    }
    if dict(sorted(gcc_checks.items())) != expected_gcc:
        raise RuntimeError(f"GNU Gzip GCC analyzer findings changed: {gcc_checks}")

    clang_text = artifacts["clang-analyzer-tidy.log"].read_text(errors="replace")
    clang_checks = Counter(re.findall(
        r"\[([A-Za-z][A-Za-z0-9_.-]*-[A-Za-z0-9_.-]+)\]$",
        clang_text,
        re.MULTILINE,
    ))
    expected_clang = {
        "bugprone-assignment-in-if-condition": 21,
        "bugprone-branch-clone": 2,
        "bugprone-easily-swappable-parameters": 25,
        "bugprone-implicit-widening-of-multiplication-result": 5,
        "bugprone-inc-dec-in-conditions": 17,
        "bugprone-macro-parentheses": 14,
        "bugprone-misplaced-widening-cast": 1,
        "bugprone-multi-level-implicit-pointer-conversion": 2,
        "bugprone-narrowing-conversions": 57,
        "bugprone-reserved-identifier": 189,
        "bugprone-signed-char-misuse": 1,
        "bugprone-sizeof-expression": 8,
        "bugprone-suspicious-include": 1,
        "clang-analyzer-core.NonNullParamChecker": 2,
        "clang-analyzer-deadcode.DeadStores": 8,
        "clang-analyzer-security.insecureAPI.DeprecatedOrUnsafeBufferHandling": 86,
        "clang-analyzer-security.insecureAPI.strcpy": 15,
    }
    if dict(sorted(clang_checks.items())) != expected_clang:
        raise RuntimeError(f"GNU Gzip Clang findings changed: {clang_checks}")
    clang_analyzer = {
        name: count for name, count in sorted(clang_checks.items())
        if name.startswith("clang-analyzer-")
    }

    flawfinder_text = artifacts["flawfinder.log"].read_text(errors="replace")
    flawfinder_hits = re.search(r"^Hits = (\d+)$", flawfinder_text, re.MULTILINE)
    flawfinder_lines = re.search(r"^Lines analyzed = (\d+) ", flawfinder_text, re.MULTILINE)
    if (
        not flawfinder_hits or not flawfinder_lines
        or int(flawfinder_hits.group(1)) != 205
        or int(flawfinder_lines.group(1)) != 21466
    ):
        raise RuntimeError("GNU Gzip Flawfinder summary changed")

    sparse_text = artifacts["sparse.log"].read_text(errors="replace")
    sparse_errors = len(re.findall(r" error: ", sparse_text))
    sparse_warnings = len(re.findall(r" warning: ", sparse_text))
    sparse_status = int(artifacts["sparse.status"].read_text().strip())
    if sparse_errors != 69 or sparse_warnings != 115 or sparse_status != 0:
        raise RuntimeError(
            "GNU Gzip Sparse output changed: "
            f"{sparse_errors}/{sparse_warnings}/{sparse_status}"
        )

    oracle = json.loads((repository / "evidence/gzip-1.14-oracle.json").read_text())
    if oracle["production_closure"]["translation_units"] != 69:
        raise RuntimeError("GNU Gzip oracle production closure changed")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-21",
        "release": "1.14",
        "status": "complete production audit; deterministic normalization pending",
        "scope": {
            "compile_actions": len(commands),
            "unique_sources": len(sources),
            "targets": [
                "gzip", "gunzip", "zcat", "uncompress", "gzexe", "zcmp",
                "zdiff", "zegrep", "zfgrep", "zforce", "zgrep", "zless",
                "zmore", "znew",
            ],
            "tests_and_nonselected_sources_excluded": True,
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
                "Guard the zero-length vasnprintf memset/memcpy paths so no null pointer is formed or passed to a nonnull-declared libc primitive.",
                "Make the fatal pack-level range check explicit to translation tools before indexing configuration_table.",
                "Split assignment and increment side effects out of conditions in the legacy codec state machines without changing their order.",
                "Replace the fixed-buffer strcpy/strcat name rewrites with explicit bounded copies before translation.",
                "Use the canonical portable CRC implementation for C2Rust if its x86 PCLMUL intrinsic source cannot be represented by the translator.",
            ],
            "notes": [
                "The vasnprintf null reports agree with the UBSan nonnull-attribute diagnostic observed by the canonical sanitizer run; the zero-length operation is behaviorally inert but must be normalized rather than hidden.",
                "Cppcheck's pack-level reports do not follow gzip_error's nonreturning contract; supported levels are 1 through 9 and all canonical tests pass, but an explicit control-flow boundary reduces translator ambiguity.",
                "GCC's seven xalloc leak reports stop at allocation-wrapper returns and do not follow ownership into callers; Valgrind observes every decompression allocation freed.",
                "GCC's savedir null report misses the mandatory xpalloc branch before the first memcpy, and its two ZIP trailer reports miss get_byte's fatal EOF path.",
                "Cppcheck's four errors are three inactive gnulib #error alternatives plus one parser failure, not compiler diagnostics from either production build.",
                "Sparse's 69 parser errors are confined to GCC x86 intrinsic headers and crc-x86_64-pclmul.c; GCC, Clang, sanitizers, and runtime comparisons all execute that selected implementation successfully.",
                "Remaining Tidy and Flawfinder output is primarily gnulib reserved identifiers, explicit legacy state-machine conversions, and bounded buffer-API inventory rather than a demonstrated runtime defect.",
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
        "sparse_parser_errors": sparse_errors,
        "sparse_warnings": sparse_warnings,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
