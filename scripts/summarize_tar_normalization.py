#!/usr/bin/env python3
"""Commit the deterministic GNU tar normalization evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


EXPECTED_CLOSURE_SHA256 = "31dd9e972f2643378de2dda2d1b9f8b615549ed254648c9e2cdd57c453a28175"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def closure(path: Path, compiler: str) -> tuple[int, list[str], str]:
    records = json.loads(path.read_text())
    marker = f"/normalized-{compiler}/"
    sources = sorted({
        record["file"].replace("\\", "/").split(marker, 1)[1]
        for record in records
    })
    digest = hashlib.sha256(("\n".join(sources) + "\n").encode()).hexdigest()
    return len(records), sources, digest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repository = args.repository.resolve()
    directory = repository / "work/analysis/tar-1.35/normalized"
    manifest_path = directory / "normalization.json"
    manifest = json.loads(manifest_path.read_text())
    changed_sources = ["gnu/human.c", "rmt/rmt.c", "src/tar.c"]
    if manifest.get("changed_sources") != changed_sources:
        raise RuntimeError("GNU tar normalization surface changed")

    compilers: dict[str, object] = {}
    expected_sources: list[str] | None = None
    for compiler in ("gcc", "clang", "sanitizer"):
        database = directory / f"{compiler}-compile-commands.json"
        actions, sources, digest = closure(database, compiler)
        if (actions, len(sources), digest) != (197, 197, EXPECTED_CLOSURE_SHA256):
            raise RuntimeError(f"GNU tar normalized {compiler} closure changed")
        if expected_sources is None:
            expected_sources = sources
        elif sources != expected_sources:
            raise RuntimeError("GNU tar normalized compiler closures differ")
        log = directory / f"{compiler}-check.log"
        text = log.read_text(errors="replace")
        if not all(marker in text for marker in (
            "224 tests were run", "20 tests were skipped",
            "222: xattrs: trusted.* attributes",
            "233: capabilities: binary store/restore",
            "2 failed unexpectedly",
        )):
            raise RuntimeError(f"GNU tar normalized {compiler} suite is incomplete")
        if compiler == "sanitizer" and (
            "ERROR: AddressSanitizer" in text
            or re.search(r"(?:^|\s)[^\s]+\.c:\d+(?::\d+)?: runtime error:", text)
        ):
            raise RuntimeError("GNU tar normalized sanitizer suite reported a defect")
        compilers[compiler] = {
            "compile_actions": actions,
            "production_sources": len(sources),
            "compile_database_sha256": sha256(database),
            "upstream_tests": {"run": 224, "passed": 202, "skipped": 20,
                               "capability_limited_failures": 2},
            "upstream_test_log_sha256": sha256(log),
        }

    differentials: dict[str, object] = {}
    for compiler in ("gcc", "clang"):
        path = directory / f"canonical-normalized-{compiler}-differential.json"
        data = json.loads(path.read_text())
        if ((data.get("cases"), data.get("passed")) != (18, 18)
                or data.get("public_names") != ["tar", "rmt"]):
            raise RuntimeError(f"GNU tar normalized {compiler} differential is incomplete")
        differentials[compiler] = {
            "cases": data["cases"], "passed": data["passed"], "sha256": sha256(path)
        }

    probe_path = directory / "c2rust-probe/results.json"
    probe = json.loads(probe_path.read_text())
    if ((probe.get("commands"), probe.get("passed"), probe.get("failed"))
            != (197, 197, 0)):
        raise RuntimeError("GNU tar per-unit C2Rust probe is incomplete")
    if probe.get("normalization_manifest_sha256") != sha256(manifest_path):
        raise RuntimeError("GNU tar C2Rust probe used a different normalization")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-22",
        "release": "1.35",
        "status": "deterministic normalization complete; translation pending",
        "normalization": manifest,
        "normalization_manifest_sha256": sha256(manifest_path),
        "production_closure_sha256": EXPECTED_CLOSURE_SHA256,
        "compilers": compilers,
        "canonical_normalized_differential": differentials,
        "review": {
            "canonical_algorithms_changed": False,
            "canonical_data_layout_changed": False,
            "changed_sources": changed_sources,
            "changes": [
                "export two multicall entrypoints while preserving standalone main wrappers",
                "make one same-range LP64 long-double-to-uintmax conversion explicit for C2Rust",
            ],
        },
        "translator_compatibility": {
            "backend": "C2Rust 0.22.1",
            "original_failure": (
                "gnu/human.c adjust_value: direct long double to uintmax_t conversion"
            ),
            "resolution": "deterministic same-range C normalization",
            "targeted_c_compile_passed": True,
            "targeted_translation_passed": True,
            "generated_rust_repairs": 0,
            "all_unit_probe": {
                "commands": 197,
                "passed": 197,
                "failed": 0,
                "sha256": sha256(probe_path),
            },
        },
        "next_gate": "C2Rust translation of the exact 197-source normalized closure",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"changed_sources": 3, "production_sources": 197,
                      "public_names": 2}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
