#!/usr/bin/env python3
"""Publish canonical-parity and size evidence for translated GNU patch."""

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


def test_summary(path: Path) -> dict[str, int]:
    text = path.read_text(errors="replace")
    result = {}
    for name in ("TOTAL", "PASS", "SKIP", "XFAIL", "FAIL", "XPASS", "ERROR"):
        match = re.search(rf"^# {name}:\s+(\d+)$", text, re.MULTILINE)
        if not match:
            raise RuntimeError(f"missing {name} in {path}")
        result[name.lower()] = int(match.group(1))
    expected = {"total": 49, "pass": 47, "skip": 0, "xfail": 2,
                "fail": 0, "xpass": 0, "error": 0}
    if result != expected:
        raise RuntimeError(f"translated GNU patch suite changed: {result}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/patch-2.8/hybrid"
    build = repository / "build/patch-2.8-hybrid"
    binary = build / "patch-hybrid"
    stripped = build / "patch-hybrid.stripped"
    canonical = build / "patch.canonical-stripped"

    upstream_path = analysis / "upstream-tests.log"
    upstream = test_summary(upstream_path)
    differential_path = analysis / "differential.json"
    differential = json.loads(differential_path.read_text())
    if not differential["gcc_clang_exact"] or differential["comparisons"] != 28:
        raise RuntimeError("translated GNU patch differential suite is incomplete")

    valgrind_path = analysis / "valgrind.log"
    valgrind = valgrind_path.read_text(errors="replace")
    for phrase in (
        "ERROR SUMMARY: 0 errors",
        "definitely lost: 0 bytes in 0 blocks",
        "indirectly lost: 0 bytes in 0 blocks",
        "possibly lost: 0 bytes in 0 blocks",
        "still reachable: 2,947 bytes in 15 blocks",
    ):
        if phrase not in valgrind:
            raise RuntimeError("GNU patch hybrid Valgrind smoke failed")

    dynamic = (build / "patch-hybrid.dynamic").read_text()
    needed = re.findall(r"Shared library: \[([^]]+)\]", dynamic)
    expected_needed = [
        "libattr.so.1", "libm.so.6", "libgcc_s.so.1", "libc.so.6",
        "ld-linux-x86-64.so.2",
    ]
    if needed != expected_needed:
        raise RuntimeError(f"unexpected GNU patch hybrid dependencies: {needed!r}")

    translation = json.loads((repository / "evidence/patch-2.8-c2rust.json").read_text())
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-20",
        "release": "2.8",
        "status": "complete translated hybrid at canonical parity; multicall integration pending",
        "implementation": {
            "rust_production_sources": 67,
            "rust_files": translation["stable_translation"]["rust_files"],
            "entrypoint": "rustbox_patch_main",
            "public_name": "patch",
        },
        "behavior": {
            "upstream_suite": {**upstream, "log_sha256": sha256(upstream_path)},
            "differential": differential,
            "valgrind_smokes": 1,
            "valgrind_still_reachable_bytes": 2947,
        },
        "size": {
            "translation_static_archive_bytes": translation["stable_translation"]["archive"]["bytes"],
            "linked_unstripped_bytes": binary.stat().st_size,
            "linked_stripped_bytes": stripped.stat().st_size,
            "canonical_stripped_bytes": canonical.stat().st_size,
            "linked_sections": {
                name.removeprefix("."): section(build / "patch-hybrid.sections", name)
                for name in (".text", ".rodata", ".data", ".bss")
            },
            "interpretation": "The static archive is link inventory, not release size.",
        },
        "artifacts": {
            "linked_sha256": sha256(binary),
            "stripped_sha256": sha256(stripped),
            "upstream_log_sha256": sha256(upstream_path),
            "differential_sha256": sha256(differential_path),
            "valgrind_log_sha256": sha256(valgrind_path),
        },
        "runtime_linkage": {
            "current_dynamic_needed": needed,
            "oracle_backend": "libattr",
            "final_no_dt_needed_gate": "pending Rustbox-owned static runtime and attr implementation",
        },
        "input_evidence": {
            name: sha256(repository / f"evidence/{name}")
            for name in (
                "patch-2.8-oracle.json",
                "patch-2.8-normalization.json",
                "patch-2.8-c2rust.json",
            )
        },
        "next_gate": "link patch into the single Rustbox multicall and replay combined regressions",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "differential": differential["comparisons"],
        "tests": upstream["total"],
        "stripped_bytes": stripped.stat().st_size,
        "text_bytes": evidence["size"]["linked_sections"]["text"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
