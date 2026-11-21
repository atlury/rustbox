#!/usr/bin/env python3
"""Publish canonical-parity and size evidence for translated attr tools."""

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


def test_summary(path: Path) -> dict[str, int]:
    text = path.read_text(errors="replace")
    result = {}
    for name in ("TOTAL", "PASS", "SKIP", "XFAIL", "FAIL", "XPASS", "ERROR"):
        match = re.search(rf"^# {name}:\s+(\d+)$", text, re.MULTILINE)
        if not match:
            raise RuntimeError(f"missing {name} in {path}")
        result[name.lower()] = int(match.group(1))
    expected = {"total": 3, "pass": 2, "skip": 1, "xfail": 0, "fail": 0, "xpass": 0, "error": 0}
    if result != expected:
        raise RuntimeError(f"translated attr upstream suite changed: {result}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/attr-2.6.0/hybrid"
    build = repository / "build/attr-2.6.0-hybrid"

    differential_path = analysis / "differential.json"
    differential = json.loads(differential_path.read_text())
    if differential.get("cases") != 22 or differential.get("passed") != 22:
        raise RuntimeError("translated attr differential suite is incomplete")
    upstream_path = analysis / "upstream-tests.log"
    upstream = test_summary(upstream_path)

    valgrind = {}
    for utility, expected in {
        "setfattr": [
            "in use at exit: 256 bytes in 1 blocks",
            "total heap usage: 1 allocs, 0 frees, 256 bytes allocated",
        ],
        "getfattr": [
            "in use at exit: 2,152 bytes in 42 blocks",
            "total heap usage: 48 allocs, 6 frees, 7,264 bytes allocated",
        ],
    }.items():
        canonical_heap = analysis / f"valgrind-{utility}-canonical-heap"
        hybrid_heap = analysis / f"valgrind-{utility}-hybrid-heap"
        if canonical_heap.read_bytes() != hybrid_heap.read_bytes():
            raise RuntimeError(f"translated attr {utility} allocation lifecycle differs")
        if hybrid_heap.read_text().splitlines()[1:] != expected:
            raise RuntimeError(f"translated attr {utility} allocation baseline changed")
        logs = {}
        for implementation in ("canonical", "hybrid"):
            log = analysis / f"valgrind-{utility}-{implementation}.log"
            if "ERROR SUMMARY: 0 errors" not in log.read_text(errors="replace"):
                raise RuntimeError(f"attr {utility} {implementation} Valgrind errors")
            logs[implementation] = sha256(log)
        valgrind[utility] = {
            "allocation_lifecycle_exact": True,
            "heap_summary": expected,
            "errors": 0,
            "log_sha256": logs,
        }

    expected_needed = ["libm.so.6", "libgcc_s.so.1", "libc.so.6", "ld-linux-x86-64.so.2"]
    binaries = {}
    for utility in ("attr", "getfattr", "setfattr"):
        binary = build / f"{utility}-hybrid"
        stripped = build / f"{utility}-hybrid.stripped"
        canonical = build / f"{utility}.canonical-stripped"
        dynamic = build / f"{utility}-hybrid.dynamic"
        if needed(dynamic) != expected_needed:
            raise RuntimeError(f"unexpected attr {utility} dependencies: {needed(dynamic)!r}")
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

    translation = json.loads((repository / "evidence/attr-2.6.0-c2rust.json").read_text())
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-21",
        "release": "2.6.0",
        "status": "complete translated hybrid at canonical parity; multicall integration pending",
        "implementation": {
            "rust_production_sources": 21,
            "rust_files": translation["stable_translation"]["rust_files"],
            "public_names": ["attr", "getfattr", "setfattr"],
            "entrypoints": ["rustbox_attr_main", "rustbox_getfattr_main", "rustbox_setfattr_main"],
            "generated_rust_repairs": 0,
            "c_abi_glue": "entrypoint only",
        },
        "behavior": {
            "upstream_tests": upstream,
            "upstream_log_sha256": sha256(upstream_path),
            "differential": differential,
            "differential_sha256": sha256(differential_path),
            "valgrind": valgrind,
        },
        "size": {
            "translation_static_archive_bytes": translation["stable_translation"]["archive"]["bytes"],
            "binaries": binaries,
            "separate_stripped_total_bytes": sum(item["linked_stripped_bytes"] for item in binaries.values()),
            "interpretation": "The static archive is link inventory, not release size; Rust runtime code is shared after multicall integration.",
        },
        "configuration": {"nls": False, "selinux": False, "systemd": False},
        "input_evidence": {
            name: sha256(repository / f"evidence/{name}")
            for name in (
                "attr-2.6.0-oracle.json",
                "attr-2.6.0-analysis.json",
                "attr-2.6.0-normalization.json",
                "attr-2.6.0-c2rust.json",
            )
        },
        "next_gate": "namespace and link attr, getfattr, and setfattr into the unified Rustbox dispatcher",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "differential": differential["passed"],
        "stripped_bytes": evidence["size"]["separate_stripped_total_bytes"],
        "upstream_pass": upstream["pass"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
