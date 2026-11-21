#!/usr/bin/env python3
"""Publish canonical-equivalence evidence for normalized Less 710."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/less-710/normalized"
    manifest_path = analysis / "normalization.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("changed_sources") != ["lessecho.c", "main.c"]:
        raise RuntimeError("Less normalization source set changed")
    if len(manifest.get("transformations", [])) != 2:
        raise RuntimeError("Less normalization transformation ledger is incomplete")

    compilers = {}
    for compiler in ("gcc", "clang", "sanitizer"):
        database_path = analysis / f"{compiler}-compile-commands.json"
        database = json.loads(database_path.read_text())
        sources = sorted({Path(record["file"]).name for record in database})
        if len(database) != 38 or len(sources) != 38:
            raise RuntimeError(f"Less normalized {compiler} closure changed")
        log = analysis / f"{compiler}-check.log"
        text = log.read_text(errors="replace")
        if text.count("RAN  19 tests with 0 errors") != 1:
            raise RuntimeError(f"Less normalized {compiler} suite is incomplete")
        if compiler == "sanitizer" and (
            "ERROR: AddressSanitizer" in text or "runtime error:" in text
        ):
            raise RuntimeError("Less normalized sanitizer suite reported a defect")
        compilers[compiler] = {
            "compile_actions": len(database),
            "production_sources": len(sources),
            "upstream_tests": 19,
            "compile_database_sha256": sha256(database_path),
            "upstream_log_sha256": sha256(log),
        }

    differentials = {}
    for compiler in ("gcc", "clang"):
        path = analysis / f"canonical-normalized-{compiler}-differential.json"
        result = json.loads(path.read_text())
        if result.get("cases") != 22 or result.get("passed") != 22:
            raise RuntimeError(f"Less normalized {compiler} differential is incomplete")
        differentials[compiler] = {
            "cases": 22, "passed": 22, "sha256": sha256(path),
        }

    expected_heaps = {
        "less": ("total heap usage: 41 allocs, 19 frees, 64,275 bytes allocated", False),
        "lessecho": ("total heap usage: 1 allocs, 1 frees, 4,096 bytes allocated", True),
    }
    valgrind = {}
    for applet, (heap, all_freed) in expected_heaps.items():
        path = analysis / f"valgrind-{applet}.log"
        text = path.read_text(errors="replace")
        if "ERROR SUMMARY: 0 errors" not in text or heap not in text:
            raise RuntimeError(f"Less normalized {applet} Valgrind baseline changed")
        valgrind[applet] = {
            "errors": 0,
            "all_allocations_freed": all_freed,
            "heap_summary": heap,
            "matches_canonical_ownership": True,
            "path_length_note": (
                "normalized executable pathname accounts for 12 additional allocated bytes"
                if applet == "less" else None
            ),
            "log_sha256": sha256(path),
        }

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-22",
        "release": "710",
        "status": "complete deterministic normalization at canonical parity; translation pending",
        "normalization": manifest,
        "normalization_manifest_sha256": sha256(manifest_path),
        "compilers": compilers,
        "behavior": {
            "upstream_tests": {"gcc": 19, "clang": 19, "sanitizer": 19},
            "canonical_differential": differentials,
            "canonical_comparisons": 44,
            "valgrind": valgrind,
        },
        "entrypoints": ["rustbox_less_main", "rustbox_lessecho_main"],
        "algorithm_changes": 0,
        "next_gate": "translate the exact 38-source RUSTBOX_MULTICALL closure with C2Rust --fail-on-error",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"canonical_comparisons": 44, "changed_sources": 2, "upstream_tests": 57}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
