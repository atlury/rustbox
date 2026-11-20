#!/usr/bin/env python3
"""Summarize the production-only GNU M4 static-analysis pass."""

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
    analysis = repository / "work/analysis/m4-1.4.21/analyzers"
    logs = {
        name: analysis / name
        for name in (
            "cppcheck.log",
            "gcc-analyzer.log",
            "clang-analyzer-tidy.log",
            "flawfinder.log",
        )
    }
    for path in logs.values():
        if not path.is_file():
            raise RuntimeError(f"missing analyzer log: {path}")

    cppcheck_text = logs["cppcheck.log"].read_text(errors="replace")
    cppcheck = Counter(
        re.findall(
            r"^/rustbox-m4/source/.*?:\d+:\d+: "
            r"(error|warning|style|performance|portability|information):",
            cppcheck_text,
            re.MULTILINE,
        )
    )
    gcc_text = logs["gcc-analyzer.log"].read_text(errors="replace")
    gcc_warnings = len(re.findall(r"warning: ", gcc_text))
    clang_text = logs["clang-analyzer-tidy.log"].read_text(errors="replace")
    clang_checks = Counter(re.findall(r"\[([A-Za-z0-9_.-]+)\]$", clang_text, re.MULTILINE))
    clang_analyzer = {
        name: count for name, count in sorted(clang_checks.items())
        if name.startswith("clang-analyzer-")
    }
    flawfinder_text = logs["flawfinder.log"].read_text(errors="replace")
    flawfinder_hits = re.search(r"^Hits = (\d+)$", flawfinder_text, re.MULTILINE)
    flawfinder_lines = re.search(r"^Lines analyzed = (\d+) ", flawfinder_text, re.MULTILINE)
    if not flawfinder_hits or not flawfinder_lines:
        raise RuntimeError("incomplete Flawfinder summary")

    oracle = json.loads((repository / "evidence/m4-1.4.21-oracle.json").read_text())
    if oracle["production"]["clang_link_source_count"] != 192:
        raise RuntimeError("M4 oracle production closure changed")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-20",
        "release": "1.4.21",
        "scope": {
            "compile_commands": 192,
            "application_sources": 11,
            "test_support_commands_excluded": 31,
        },
        "tools": {
            "cppcheck": {"findings_by_severity": dict(sorted(cppcheck.items()))},
            "gcc_fanalyzer": {"warnings": gcc_warnings},
            "clang_analyzer_tidy": {
                "analyzer_findings_by_check": clang_analyzer,
                "all_findings_by_check": dict(sorted(clang_checks.items())),
            },
            "flawfinder": {
                "hits_at_level_1_or_higher": int(flawfinder_hits.group(1)),
                "lines_analyzed": int(flawfinder_lines.group(1)),
            },
        },
        "review": {
            "blocking_findings": 0,
            "notes": [
                "GCC ownership warnings are returned allocations, registered cleanup state, or xmalloc-family wrappers; Valgrind reports zero definitely, indirectly, or possibly lost bytes.",
                "Clang's INPUT_STRING null path contradicts all constructors, which assign obstack-backed non-null strings; both full suites and the sanitizer language suite do not reproduce it.",
                "Clang vasnprintf null paths lose the allocation postcondition through gnulib macros; the bundled gnulib suite and sanitizer run cover those paths without reproduction.",
                "Clang enum-range reports are intentional bitwise combinations of canonicalize mode flags; strcpy reports have explicitly sized destinations.",
                "Cppcheck preprocessor and uninitialized reports include unsupported generated-header configurations; compiler analyzers and runtime gates take precedence.",
                "All findings remain recorded for normalization and later pointer/no_std hardening even when not reproduced dynamically.",
            ],
        },
        "logs": {name: sha256(path) for name, path in logs.items()},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "cppcheck": sum(cppcheck.values()),
        "gcc": gcc_warnings,
        "clang_analyzer": sum(clang_analyzer.values()),
        "flawfinder": int(flawfinder_hits.group(1)),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
