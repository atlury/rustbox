#!/usr/bin/env python3
"""Publish canonical-parity and size evidence for translated GNU bc and dc."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def section(path: Path, name: str) -> int:
    match = re.search(rf"^{re.escape(name)}\s+(\d+)\s+", path.read_text(), re.MULTILINE)
    if not match:
        raise RuntimeError(f"missing {name} in {path}")
    return int(match.group(1))


def needed(path: Path) -> list[str]:
    return re.findall(r"Shared library: \[([^]]+)\]", path.read_text())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/bc-1.08.2/hybrid"
    build = repository / "build/bc-1.08.2-hybrid"

    differential_path = analysis / "differential.json"
    differential = json.loads(differential_path.read_text())
    if differential["cases"] != 46 or differential["passed"] != 46:
        raise RuntimeError("translated GNU bc/dc differential suite is incomplete")

    workloads = analysis.joinpath("upstream-tests.log").read_text().splitlines()
    if len(workloads) != 18 or any(not line.endswith(" pass") for line in workloads):
        raise RuntimeError(f"GNU bc shipped workload results changed: {workloads!r}")
    if "checklib.b pass" not in workloads:
        raise RuntimeError("GNU bc exhaustive checklib.b workload is missing")

    valgrind = {}
    for utility, expected in {
        "bc": [
            "in use at exit: 52,619 bytes in 53 blocks",
            "total heap usage: 66 allocs, 13 frees, 56,826 bytes allocated",
        ],
        "dc": [
            "in use at exit: 376 bytes in 13 blocks",
            "total heap usage: 37 allocs, 24 frees, 8,774 bytes allocated",
        ],
    }.items():
        canonical_heap = analysis / f"valgrind-{utility}-canonical-heap"
        hybrid_heap = analysis / f"valgrind-{utility}-hybrid-heap"
        if canonical_heap.read_bytes() != hybrid_heap.read_bytes():
            raise RuntimeError(f"GNU {utility} translated allocation lifecycle differs")
        if hybrid_heap.read_text().splitlines()[1:] != expected:
            raise RuntimeError(f"GNU {utility} allocation baseline changed")
        logs = {}
        for implementation in ("canonical", "hybrid"):
            log = analysis / f"valgrind-{utility}-{implementation}.log"
            if "ERROR SUMMARY: 0 errors" not in log.read_text(errors="replace"):
                raise RuntimeError(f"GNU {utility} {implementation} Valgrind errors")
            logs[implementation] = sha256(log)
        valgrind[utility] = {
            "allocation_lifecycle_exact": True,
            "heap_summary": expected,
            "errors": 0,
            "log_sha256": logs,
        }

    expected_needed = ["libm.so.6", "libgcc_s.so.1", "libc.so.6", "ld-linux-x86-64.so.2"]
    binaries = {}
    for utility in ("bc", "dc"):
        binary = build / f"{utility}-hybrid"
        stripped = build / f"{utility}-hybrid.stripped"
        canonical = build / f"{utility}.canonical-stripped"
        dynamic = build / f"{utility}-hybrid.dynamic"
        if needed(dynamic) != expected_needed:
            raise RuntimeError(f"unexpected GNU {utility} dependencies: {needed(dynamic)!r}")
        binaries[utility] = {
            "linked_unstripped_bytes": binary.stat().st_size,
            "linked_stripped_bytes": stripped.stat().st_size,
            "canonical_stripped_bytes": canonical.stat().st_size,
            "linked_sha256": sha256(binary),
            "stripped_sha256": sha256(stripped),
            "sections": {
                name.removeprefix("."): section(build / f"{utility}-hybrid.sections", name)
                for name in (".text", ".rodata", ".data", ".bss")
            },
            "dynamic_needed": expected_needed,
        }

    translation = json.loads((repository / "evidence/bc-1.08.2-c2rust.json").read_text())
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-21",
        "release": "1.08.2",
        "bundled_dc_release": "1.5.2",
        "status": "complete translated hybrid at canonical parity; multicall integration pending",
        "implementation": {
            "rust_production_sources": 21,
            "rust_files": translation["stable_translation"]["rust_files"],
            "public_names": ["bc", "dc"],
            "entrypoints": ["rustbox_bc_main", "rustbox_dc_main"],
            "generated_rust_repairs": 0,
            "c_abi_glue": "entrypoint only",
        },
        "behavior": {
            "shipped_workloads": len(workloads),
            "exhaustive_checklib": True,
            "workload_log_sha256": sha256(analysis / "upstream-tests.log"),
            "differential": differential,
            "valgrind": valgrind,
        },
        "size": {
            "translation_static_archive_bytes": translation["stable_translation"]["archive"]["bytes"],
            "binaries": binaries,
            "interpretation": "The static archive is link inventory, not release size.",
        },
        "configuration": {
            "selinux": False,
            "systemd": False,
            "readline": False,
            "libedit": False,
        },
        "input_evidence": {
            name: sha256(repository / f"evidence/{name}")
            for name in (
                "bc-1.08.2-oracle.json",
                "bc-1.08.2-analysis.json",
                "bc-1.08.2-normalization.json",
                "bc-1.08.2-c2rust.json",
            )
        },
        "next_gate": "namespace and link bc and dc into the unified Rustbox dispatcher",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "differential": differential["passed"],
        "shipped_workloads": len(workloads),
        "stripped_bytes": sum(item["linked_stripped_bytes"] for item in binaries.values()),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
