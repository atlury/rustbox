#!/usr/bin/env python3
"""Publish canonical-parity and size evidence for translated GNU Grep."""

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


def test_summaries(path: Path) -> list[dict[str, int]]:
    text = path.read_text(errors="replace")
    matches = re.findall(
        r"# TOTAL:\s+(\d+).*?# PASS:\s+(\d+).*?# SKIP:\s+(\d+).*?"
        r"# XFAIL:\s+(\d+).*?# FAIL:\s+(\d+).*?# XPASS:\s+(\d+).*?# ERROR:\s+(\d+)",
        text,
        re.DOTALL,
    )
    names = ("total", "pass", "skip", "xfail", "fail", "xpass", "error")
    result = [dict(zip(names, map(int, values))) for values in matches]
    expected = [
        {"total": 128, "pass": 113, "skip": 13, "xfail": 2, "fail": 0, "xpass": 0, "error": 0},
        {"total": 315, "pass": 277, "skip": 38, "xfail": 0, "fail": 0, "xpass": 0, "error": 0},
    ]
    if result != expected:
        raise RuntimeError(f"translated GNU Grep suites changed: {result}")
    return result


def check_valgrind(analysis: Path) -> dict[str, object]:
    expected = (
        "ERROR SUMMARY: 3 errors",
        "definitely lost: 0 bytes in 0 blocks",
        "indirectly lost: 0 bytes in 0 blocks",
        "possibly lost: 18,688 bytes in 11 blocks",
        "still reachable: 119,466 bytes in 39 blocks",
    )
    logs = {}
    for implementation in ("hybrid", "canonical"):
        path = analysis / f"valgrind-{implementation}.log"
        text = path.read_text(errors="replace")
        if not all(phrase in text for phrase in expected):
            raise RuntimeError(f"GNU Grep {implementation} Valgrind baseline changed")
        logs[implementation] = sha256(path)
    hybrid_heap = (analysis / "valgrind-hybrid-heap").read_text()
    canonical_heap = (analysis / "valgrind-canonical-heap").read_text()
    expected_heap = (
        "HEAP SUMMARY:\n"
        "in use at exit: 138,154 bytes in 50 blocks\n"
        "total heap usage: 202 allocs, 152 frees, 166,596 bytes allocated\n"
    )
    if hybrid_heap != canonical_heap or hybrid_heap != expected_heap:
        raise RuntimeError("GNU Grep translated allocation lifecycle differs from canonical")
    return {
        "allocation_lifecycle_exact": True,
        "heap_summary": hybrid_heap.splitlines()[1:],
        "errors": 3,
        "definitely_lost_bytes": 0,
        "indirectly_lost_bytes": 0,
        "possibly_lost_bytes": 18688,
        "reachable_bytes": 119466,
        "log_sha256": logs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/grep-3.12/hybrid"
    build = repository / "build/grep-3.12-hybrid"

    upstream_path = analysis / "upstream-tests.log"
    upstream = test_summaries(upstream_path)
    differential_path = analysis / "differential.json"
    differential = json.loads(differential_path.read_text())
    if not differential["gcc_clang_exact"] or differential["comparisons"] != 36:
        raise RuntimeError("translated GNU Grep differential suite is incomplete")
    valgrind = check_valgrind(analysis)

    binary = build / "grep-hybrid"
    stripped = build / "grep-hybrid.stripped"
    canonical = build / "grep.canonical-stripped"
    dynamic = (build / "grep-hybrid.dynamic").read_text()
    needed = re.findall(r"Shared library: \[([^]]+)\]", dynamic)
    expected_needed = [
        "libpcre2-8.so.0", "libm.so.6", "libgcc_s.so.1", "libc.so.6",
        "ld-linux-x86-64.so.2",
    ]
    if needed != expected_needed:
        raise RuntimeError(f"unexpected GNU Grep hybrid dependencies: {needed!r}")

    translation = json.loads((repository / "evidence/grep-3.12-c2rust.json").read_text())
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-21",
        "release": "3.12",
        "status": "complete translated hybrid at canonical parity; multicall integration pending",
        "implementation": {
            "rust_production_sources": 129,
            "rust_files": translation["stable_translation"]["rust_files"],
            "public_names": ["grep", "egrep", "fgrep"],
            "entrypoint": "rustbox_grep_main",
            "generated_rust_repairs": 0,
            "abi_wrappers": {
                "__btowc_alias": "btowc",
                "__wctob_alias": "wctob",
            },
        },
        "behavior": {
            "upstream_suites": upstream,
            "upstream_total": sum(summary["total"] for summary in upstream),
            "differential": differential,
            "valgrind": valgrind,
        },
        "size": {
            "translation_static_archive_bytes": translation["stable_translation"]["archive"]["bytes"],
            "linked_unstripped_bytes": binary.stat().st_size,
            "linked_stripped_bytes": stripped.stat().st_size,
            "canonical_stripped_bytes": canonical.stat().st_size,
            "linked_sections": {
                name.removeprefix("."): section(build / "grep-hybrid.sections", name)
                for name in (".text", ".rodata", ".data", ".bss")
            },
            "linked_sha256": sha256(binary),
            "stripped_sha256": sha256(stripped),
            "interpretation": "The static archive is link inventory, not release size.",
        },
        "artifacts": {
            "upstream_log_sha256": sha256(upstream_path),
            "differential_sha256": sha256(differential_path),
        },
        "runtime_linkage": {
            "current_dynamic_needed": needed,
            "pcre2_preserved": True,
            "selinux": False,
            "systemd": False,
            "final_no_dt_needed_gate": "pending Rustbox-owned static runtime and PCRE2 integration",
        },
        "input_evidence": {
            name: sha256(repository / f"evidence/{name}")
            for name in (
                "grep-3.12-oracle.json",
                "grep-3.12-analysis.json",
                "grep-3.12-normalization.json",
                "grep-3.12-c2rust.json",
            )
        },
        "next_gate": "link grep, egrep, and fgrep into Rustbox and replay combined regressions",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "differential": differential["comparisons"],
        "tests": evidence["behavior"]["upstream_total"],
        "stripped_bytes": stripped.stat().st_size,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
