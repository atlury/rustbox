#!/usr/bin/env python3
"""Summarize deterministic XZ 5.8.4 normalization and canonical parity."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


CLOSURE = "1d9270fb42e95e59fd9bbc00a583d21d5cf84896cac89b4a5ab429d38cb7f7a2"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    root = repository / "work/analysis/xz-5.8.4/normalized"
    manifest_path = root / "normalization.json"
    manifest = json.loads(manifest_path.read_text())
    changed = ["src/lzmainfo/lzmainfo.c", "src/xz/main.c", "src/xzdec/xzdec.c"]
    if manifest.get("changed_sources") != changed or manifest.get("entrypoints") != 4:
        raise RuntimeError("XZ normalization manifest changed")

    compilers: dict[str, object] = {}
    for compiler in ("gcc", "clang", "sanitizer"):
        database = root / f"{compiler}-compile-commands.json"
        records = json.loads(database.read_text())
        marker = f"/normalized-{compiler}/"
        sources = sorted({record["file"].replace("\\", "/").split(marker, 1)[1]
                          for record in records})
        closure = hashlib.sha256(("\n".join(sources) + "\n").encode()).hexdigest()
        if len(records) != 113 or len(sources) != 101 or closure != CLOSURE:
            raise RuntimeError(f"XZ normalized {compiler} closure changed")
        log = root / f"{compiler}-check.log"
        text = log.read_text(errors="replace")
        for expected in ("# TOTAL: 22", "# PASS:  22", "# SKIP:  0",
                         "# FAIL:  0", "# ERROR: 0"):
            if expected not in text:
                raise RuntimeError(f"XZ normalized {compiler} suite is incomplete")
        if compiler == "sanitizer" and (
            "ERROR: AddressSanitizer" in text
            or re.search(r"\.c:\d+(?::\d+)?: runtime error:", text)
        ):
            raise RuntimeError("XZ normalized sanitizer suite reported a defect")
        compilers[compiler] = {
            "compile_actions": len(records), "unique_sources": len(sources),
            "compile_database_sha256": sha256(database),
            "upstream_tests": {"total": 22, "passed": 22, "skipped": 0},
            "upstream_test_log_sha256": sha256(log),
            "landlock": compiler != "sanitizer", "passed": True,
        }

    differentials: dict[str, object] = {}
    for compiler in ("gcc", "clang"):
        path = root / f"canonical-normalized-{compiler}-differential.json"
        data = json.loads(path.read_text())
        if data.get("cases") != 70 or data.get("passed") != 70:
            raise RuntimeError(f"XZ normalized {compiler} parity is incomplete")
        differentials[compiler] = {"cases": 70, "passed": 70, "sha256": sha256(path)}

    evidence = {
        "schema": 1, "recorded_at": "2026-11-22", "release": "5.8.4",
        "status": "complete deterministic normalization at canonical parity; C2Rust translation pending",
        "normalization": {
            "changed_sources": changed, "entrypoints_exported": 4,
            "source_rewrites": "entrypoint identity only",
            "compiler_configuration": "upstream --disable-clmul-crc portable CRC implementation",
            "algorithm_changes": 0, "manifest_sha256": sha256(manifest_path),
            "canonical_tree_sha256": manifest["canonical_tree_sha256"],
            "normalized_tree_sha256": manifest["normalized_tree_sha256"],
        },
        "production_closure": {"compile_actions": 113, "sources": 101,
                               "sha256": CLOSURE},
        "compilers": compilers,
        "canonical_normalized_differential": differentials,
        "behavior": {"cases_per_compiler": 70, "total_comparisons": 140,
                     "passed": 140, "byte_identical_xz_streams": True,
                     "byte_identical_lzma_streams": True},
        "next_gate": "translate the exact normalized closure with complete declaration maps and no holes",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"changed_sources": 3, "entrypoints": 4,
                      "parity": 140, "upstream_tests": 66}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
