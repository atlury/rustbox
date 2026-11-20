#!/usr/bin/env python3
"""Summarize the production-only File 5.48 static-analysis pass."""

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
    analysis = repository / "work/analysis/file-5.48/analyzers"
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
    if len(compile_commands) != 25 or len(sources) != 25 or len(set(sources)) != 25:
        raise RuntimeError("File analyzer production closure changed")

    cppcheck_text = logs["cppcheck.log"].read_text(errors="replace")
    cppcheck = Counter(
        re.findall(
            r"^/rustbox-file/source/.*?:\d+:\d+: "
            r"(error|warning|style|performance|portability|information):",
            cppcheck_text,
            re.MULTILINE,
        )
    )
    cppcheck_ids = Counter(
        re.findall(
            r"^/rustbox-file/source/.*?:\d+:\d+: "
            r"(?:error|warning|style|performance|portability|information): ([A-Za-z0-9_]+):",
            cppcheck_text,
            re.MULTILINE,
        )
    )
    gcc_text = logs["gcc-analyzer.log"].read_text(errors="replace")
    gcc_warnings = len(re.findall(r"warning: ", gcc_text))
    gcc_checks = Counter(re.findall(r"\[-W(analyzer-[^]]+)\]", gcc_text))

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

    oracle = json.loads((repository / "evidence/file-5.48-oracle.json").read_text())
    if (
        oracle["scope"]["production_compile_actions"]["clang"] != 25
        or oracle["scope"]["unique_production_sources"] != 25
    ):
        raise RuntimeError("File oracle production closure changed")
    if gcc_warnings != 2 or gcc_checks != {"analyzer-use-of-uninitialized-value": 2}:
        raise RuntimeError(f"File GCC analyzer findings changed: {gcc_checks}")
    if clang_analyzer != {
        "clang-analyzer-security.insecureAPI.DeprecatedOrUnsafeBufferHandling": 226
    }:
        raise RuntimeError(f"File Clang analyzer findings changed: {clang_analyzer}")
    if len(sparse_lines) != 9:
        raise RuntimeError("File Sparse findings changed")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-20",
        "release": "5.48",
        "scope": {
            "compile_actions": len(compile_commands),
            "unique_sources": len(sources),
            "targets": ["file", "libmagic"],
            "tests_and_examples_excluded": True,
        },
        "tools": {
            "cppcheck": {
                "findings_by_severity": dict(sorted(cppcheck.items())),
                "findings_by_id": dict(sorted(cppcheck_ids.items())),
            },
            "gcc_fanalyzer": {
                "warnings": gcc_warnings,
                "findings_by_check": dict(sorted(gcc_checks.items())),
                "unique_root_causes": 1,
            },
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
            "actionable_hardening_findings": 1,
            "notes": [
                "GCC emits two diagnostics for one root cause: do_ops leaves offset uninitialized only if a nonzero operand is paired with an operation value outside every defined FILE_OP case. The canonical parser constrains that field, but normalization will initialize offset to lhs before the switch and rerun every parity gate.",
                "Cppcheck's overlappingWriteUnion reports cover the intentional endian conversion pattern that reads a union byte-array member before assigning its scalar member; GCC, Clang, ASan, UBSan, and the complete fixture corpus execute these paths without reproducing a defect.",
                "Cppcheck's single syntaxError is a parser failure on the ordinary asprintf call in magic_getpath, not a compiler diagnostic.",
                "Clang's analyzer findings are exclusively its generic Annex K replacement advice for memcpy, memset, snprintf, and related bounded calls; it reports no path-sensitive core or unix analyzer defect.",
                "Clang-Tidy bugprone/performance findings are advisory modernization sites retained for later pointer hardening rather than bulk-edited during translation normalization.",
                "Sparse's nine findings are semantics-neutral integer-zero null-pointer spellings.",
                "Flawfinder reports lexical risk sites for later pointer hardening and does not establish an executable defect by itself.",
            ],
        },
        "artifacts": {name: sha256(path) for name, path in logs.items()},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "clang_analyzer": sum(clang_analyzer.values()),
        "cppcheck": sum(cppcheck.values()),
        "flawfinder": int(flawfinder_hits.group(1)),
        "gcc": gcc_warnings,
        "sparse": len(sparse_lines),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
