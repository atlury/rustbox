#!/usr/bin/env python3
"""Publish canonical-parity and size evidence for translated acl tools."""

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


def test_summary(path: Path, expected: dict[str, int]) -> dict[str, int]:
    text = path.read_text(errors="replace")
    result = {}
    for name in ("TOTAL", "PASS", "SKIP", "XFAIL", "FAIL", "XPASS", "ERROR"):
        match = re.search(rf"^# {name}:\s+(\d+)$", text, re.MULTILINE)
        if not match:
            raise RuntimeError(f"missing {name} in {path}")
        result[name.lower()] = int(match.group(1))
    if result != expected:
        raise RuntimeError(f"translated acl upstream suite changed: {result}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/acl-2.4.0/hybrid"
    build = repository / "build/acl-2.4.0-hybrid"

    differential_path = analysis / "differential.json"
    differential = json.loads(differential_path.read_text())
    if differential.get("cases") != 30 or differential.get("passed") != 30:
        raise RuntimeError("translated acl differential suite is incomplete")
    upstream_path = analysis / "upstream-tests.log"
    upstream = test_summary(upstream_path, {
        "total": 15, "pass": 13, "skip": 0, "xfail": 2,
        "fail": 0, "xpass": 0, "error": 0,
    })
    platform_path = analysis / "platform-permissions.log"
    platform = test_summary(platform_path, {
        "total": 1, "pass": 0, "skip": 0, "xfail": 0,
        "fail": 1, "xpass": 0, "error": 0,
    })

    expected_heaps = {
        "setfacl": {
            "canonical": "total heap usage: 10 allocs, 10 frees, 786 bytes allocated",
            "hybrid": "total heap usage: 12 allocs, 12 frees, 950 bytes allocated",
        },
        "getfacl": {
            "canonical": "total heap usage: 4 allocs, 4 frees, 4,596 bytes allocated",
            "hybrid": "total heap usage: 8 allocs, 8 frees, 4,920 bytes allocated",
        },
    }
    valgrind = {}
    for utility, summaries in expected_heaps.items():
        logs = {}
        heaps = {}
        for implementation, expected in summaries.items():
            log = analysis / f"valgrind-{utility}-{implementation}.log"
            text = log.read_text(errors="replace")
            if (
                "ERROR SUMMARY: 0 errors" not in text
                or "All heap blocks were freed -- no leaks are possible" not in text
                or expected not in text
            ):
                raise RuntimeError(f"acl {utility} {implementation} Valgrind baseline changed")
            logs[implementation] = sha256(log)
            heaps[implementation] = expected
        valgrind[utility] = {
            "errors": 0,
            "all_allocations_freed": True,
            "heap_summary": heaps,
            "log_sha256": logs,
            "translation_overhead": (
                "C2Rust represents generated temporary aggregate storage with a "
                "short-lived Rust Vec; the extra allocations are fully freed"
            ),
        }
    if (
        analysis.joinpath("valgrind-getfacl-canonical.out").read_bytes()
        != analysis.joinpath("valgrind-getfacl-hybrid.out").read_bytes()
    ):
        raise RuntimeError("translated acl getfacl Valgrind output differs")

    expected_needed = ["libm.so.6", "libgcc_s.so.1", "libc.so.6", "ld-linux-x86-64.so.2"]
    binaries = {}
    for utility in ("chacl", "getfacl", "setfacl"):
        binary = build / f"{utility}-hybrid"
        stripped = build / f"{utility}-hybrid.stripped"
        canonical = build / f"{utility}.canonical-stripped"
        dynamic = build / f"{utility}-hybrid.dynamic"
        if needed(dynamic) != expected_needed:
            raise RuntimeError(f"unexpected acl {utility} dependencies: {needed(dynamic)!r}")
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

    translation = json.loads((repository / "evidence/acl-2.4.0-c2rust.json").read_text())
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-21",
        "release": "2.4.0",
        "status": "complete translated hybrid at canonical parity; multicall integration pending",
        "implementation": {
            "rust_production_sources": 72,
            "rust_files": translation["stable_translation"]["rust_files"],
            "public_names": ["chacl", "getfacl", "setfacl"],
            "entrypoints": [
                "rustbox_chacl_main", "rustbox_getfacl_main", "rustbox_setfacl_main",
            ],
            "generated_rust_repairs": 0,
            "c_abi_glue": "entrypoint only",
            "per_applet_program_name_state": True,
        },
        "behavior": {
            "upstream_tests": upstream,
            "platform_test": platform,
            "upstream_log_sha256": sha256(upstream_path),
            "platform_log_sha256": sha256(platform_path),
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
                "acl-2.4.0-oracle.json", "acl-2.4.0-analysis.json",
                "acl-2.4.0-normalization.json", "acl-2.4.0-c2rust.json",
            )
        },
        "next_gate": "namespace and link chacl, getfacl, and setfacl into the unified Rustbox dispatcher",
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
