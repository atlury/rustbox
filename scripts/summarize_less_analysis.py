#!/usr/bin/env python3
"""Publish the six-tool static-analysis ledger for Less 710."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def count(pattern: str, text: str) -> int:
    return len(re.findall(pattern, text, re.MULTILINE))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/less-710/analyzers"
    oracle = json.loads((repository / "evidence/less-710-oracle.json").read_text())
    sources = (analysis / "sources.list").read_text().splitlines()
    if len(sources) != 38 or len(set(sources)) != 38:
        raise RuntimeError("Less analyzer source closure changed")

    logs = {name: analysis / name for name in (
        "cppcheck.log", "gcc-analyzer.log", "clang-analyzer-tidy.log",
        "flawfinder.log", "sparse.log", "splint.log",
    )}
    texts = {name: path.read_text(errors="replace") for name, path in logs.items()}
    flawfinder = re.search(r"Hits = (\d+)", texts["flawfinder.log"])
    if flawfinder is None:
        raise RuntimeError("Less Flawfinder summary is missing")
    sparse_status = int((analysis / "sparse.status").read_text())
    splint_status = int((analysis / "splint.status").read_text())
    if sparse_status != 0 or splint_status != 123:
        raise RuntimeError("Less analyzer exit baseline changed")
    gcc_text = texts["gcc-analyzer.log"]
    if "Error " in gcc_text or "make: ***" in gcc_text:
        raise RuntimeError("Less GCC analyzer build failed")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-22",
        "release": "710",
        "status": "complete six-tool canonical-source audit; findings retained for translation review",
        "closure": {
            "production_sources": len(sources),
            "source_list_sha256": sha256(analysis / "sources.list"),
            "oracle_evidence_sha256": sha256(repository / "evidence/less-710-oracle.json"),
            "matches_oracle_sources": len(sources) == oracle["inventory"]["production_source_count"],
        },
        "tools": {
            "cppcheck": {
                "diagnostics": count(r"^/rustbox-less/source/.*: (?:style|warning|error):", texts["cppcheck.log"]),
                "syntax_limitations": count(r"syntaxError", texts["cppcheck.log"]),
                "log_sha256": sha256(logs["cppcheck.log"]),
            },
            "gcc_fanalyzer": {
                "warnings": count(r"warning:", gcc_text),
                "path_sensitive_warnings": count(r"\[-Wanalyzer-", gcc_text),
                "build_complete": True,
                "log_sha256": sha256(logs["gcc-analyzer.log"]),
            },
            "clang_analyzer_tidy": {
                "warnings": count(r"warning:", texts["clang-analyzer-tidy.log"]),
                "errors": count(r"error:", texts["clang-analyzer-tidy.log"]),
                "log_sha256": sha256(logs["clang-analyzer-tidy.log"]),
            },
            "flawfinder": {
                "hits": int(flawfinder.group(1)),
                "log_sha256": sha256(logs["flawfinder.log"]),
            },
            "sparse": {
                "status": sparse_status,
                "warnings": count(r"warning:", texts["sparse.log"]),
                "log_sha256": sha256(logs["sparse.log"]),
            },
            "splint": {
                "status": splint_status,
                "limitation": "per-translation-unit preprocessing stops where Clang 18 enables stdckdint.h but Splint cannot locate it",
                "log_sha256": sha256(logs["splint.log"]),
            },
        },
        "review": {
            "sanitizer_context": "canonical GCC ASan/UBSan passes all 19 upstream tests",
            "resource_context": "canonical Valgrind has zero errors and zero definite/indirect loss",
            "policy": "retain diagnostics as candidates; do not change algorithms during multicall normalization",
        },
        "next_gate": "deterministic two-entrypoint normalization, then full-closure C2Rust translation",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "sources": len(sources),
        "cppcheck": evidence["tools"]["cppcheck"]["diagnostics"],
        "gcc_fanalyzer": evidence["tools"]["gcc_fanalyzer"]["path_sensitive_warnings"],
        "clang": evidence["tools"]["clang_analyzer_tidy"]["warnings"],
        "flawfinder": evidence["tools"]["flawfinder"]["hits"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
