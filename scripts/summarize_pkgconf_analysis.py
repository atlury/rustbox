#!/usr/bin/env python3
"""Summarize the production-only pkgconf static-analysis pass."""

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
    analysis = repository / "work/analysis/pkgconf-3.0.11/analyzers"
    names = (
        "compile_commands.json",
        "sources.list",
        "cppcheck.log",
        "gcc-analyzer-setup.log",
        "gcc-analyzer.log",
        "clang-analyzer-tidy.log",
        "flawfinder.log",
        "sparse.log",
    )
    logs = {name: analysis / name for name in names}
    for path in logs.values():
        if not path.is_file():
            raise RuntimeError(f"missing analyzer artifact: {path}")

    compile_commands = json.loads(logs["compile_commands.json"].read_text())
    sources = [line for line in logs["sources.list"].read_text().splitlines() if line]
    if len(compile_commands) != 38 or len(sources) != 35 or len(set(sources)) != 35:
        raise RuntimeError(
            f"pkgconf production closure changed: actions={len(compile_commands)}, "
            f"sources={len(sources)}, unique={len(set(sources))}"
        )

    cppcheck_text = logs["cppcheck.log"].read_text(errors="replace")
    cppcheck = Counter(
        re.findall(
            r"^/rustbox-pkgconf/source/.*?:\d+:\d+: "
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
        name: count
        for name, count in sorted(clang_checks.items())
        if name.startswith("clang-analyzer-")
    }
    flawfinder_text = logs["flawfinder.log"].read_text(errors="replace")
    flawfinder_hits = re.search(r"^Hits = (\d+)$", flawfinder_text, re.MULTILINE)
    flawfinder_lines = re.search(r"^Lines analyzed = (\d+) ", flawfinder_text, re.MULTILINE)
    if not flawfinder_hits or not flawfinder_lines:
        raise RuntimeError("incomplete Flawfinder summary")
    sparse_lines = [line for line in logs["sparse.log"].read_text(errors="replace").splitlines() if line]

    oracle = json.loads((repository / "evidence/pkgconf-3.0.11-oracle.json").read_text())
    if (
        oracle["scope"]["production_compile_actions"] != {"clang": 38, "gcc": 38}
        or oracle["scope"]["unique_production_sources"] != 35
    ):
        raise RuntimeError("pkgconf oracle production closure changed")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-20",
        "release": "3.0.11",
        "scope": {
            "compile_actions": len(compile_commands),
            "unique_sources": len(sources),
            "targets": ["libpkgconf", "pkgconf", "bomtool", "pccritic", "spdxtool"],
            "tests_and_benchmarks_excluded": True,
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
            "sparse": {"warnings": len(sparse_lines)},
        },
        "review": {
            "blocking_findings": 0,
            "notes": [
                "Clang's pccritic fileno warning loses the invariant that out is assigned stdout before option parsing and is never assigned null.",
                "Clang's bomtool fclose warning likewise loses the invariant that sbom_out is assigned stdout before parsing and every later assignment is checked for null.",
                "Sparse identifies one bitwise-or spelling between already-evaluated boolean allocation checks in spdxtool; it has the same truth value and no evaluation-side-effect difference, and will be made explicit in normalization.",
                "GCC -fanalyzer reports no warnings for the exact production executable closure.",
                "Cppcheck findings are style or portability reports; compiler analyzers, the complete sanitizer suite, and the complete static Valgrind suite do not reproduce a memory-safety failure.",
                "Flawfinder reports lexical risk sites for later pointer hardening; it does not establish an executable defect by itself.",
                "All findings remain recorded for normalization and later raw-pointer/no_std hardening.",
            ],
        },
        "artifacts": {name: sha256(path) for name, path in logs.items()},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "cppcheck": sum(cppcheck.values()),
                "gcc": gcc_warnings,
                "clang_analyzer": sum(clang_analyzer.values()),
                "flawfinder": int(flawfinder_hits.group(1)),
                "sparse": len(sparse_lines),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
