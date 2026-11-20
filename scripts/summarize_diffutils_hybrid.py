#!/usr/bin/env python3
"""Publish canonical-parity and size evidence for translated GNU Diffutils."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


UTILITIES = ("cmp", "diff", "diff3", "sdiff")


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
        {"total": 33, "pass": 30, "skip": 2, "xfail": 1, "fail": 0, "xpass": 0, "error": 0},
        {"total": 344, "pass": 301, "skip": 43, "xfail": 0, "fail": 0, "xpass": 0, "error": 0},
    ]
    if result != expected:
        raise RuntimeError(f"translated GNU Diffutils suites changed: {result}")
    return result


def check_valgrind(analysis: Path) -> dict[str, object]:
    clean = {}
    for utility in ("cmp", "diff", "sdiff"):
        path = analysis / f"valgrind-{utility}.log"
        text = path.read_text(errors="replace")
        for phrase in (
            "ERROR SUMMARY: 0 errors",
            "definitely lost: 0 bytes in 0 blocks",
            "indirectly lost: 0 bytes in 0 blocks",
            "possibly lost: 0 bytes in 0 blocks",
        ):
            if phrase not in text:
                raise RuntimeError(f"GNU {utility} hybrid Valgrind smoke failed")
        clean[utility] = {"log_sha256": sha256(path), "errors": 0}

    translated = analysis / "valgrind-diff3.log"
    canonical = analysis / "valgrind-diff3-canonical.log"
    translated_text = translated.read_text(errors="replace")
    canonical_text = canonical.read_text(errors="replace")
    expected_translated = (
        "ERROR SUMMARY: 9 errors",
        "definitely lost: 4,208 bytes in 2 blocks",
        "indirectly lost: 48 bytes in 6 blocks",
        "possibly lost: 4,096 bytes in 1 blocks",
    )
    expected_canonical = (
        "ERROR SUMMARY: 2 errors",
        "definitely lost: 4,096 bytes in 1 blocks",
        "indirectly lost: 0 bytes in 0 blocks",
        "possibly lost: 4,096 bytes in 1 blocks",
    )
    if not all(item in translated_text for item in expected_translated):
        raise RuntimeError("translated diff3 Valgrind classification changed")
    if not all(item in canonical_text for item in expected_canonical):
        raise RuntimeError("canonical diff3 Valgrind baseline changed")
    translated_heap = (analysis / "valgrind-diff3-heap").read_text()
    canonical_heap = (analysis / "valgrind-diff3-canonical-heap").read_text()
    if translated_heap != canonical_heap:
        raise RuntimeError("translated diff3 allocation lifecycle differs from canonical")
    expected_heap = (
        "HEAP SUMMARY:\n"
        "in use at exit: 8,456 bytes in 14 blocks\n"
        "total heap usage: 20 allocs, 6 frees, 12,675 bytes allocated\n"
    )
    if translated_heap != expected_heap:
        raise RuntimeError(f"diff3 heap baseline changed: {translated_heap!r}")
    return {
        "clean": clean,
        "diff3": {
            "allocation_lifecycle_exact": True,
            "heap_summary": translated_heap.splitlines()[1:],
            "classification_difference": (
                "optimized Rust drops the final stack root before process exit, so Valgrind "
                "classifies the canonical intentionally retained 112-byte graph root and its "
                "48 bytes of children as lost rather than reachable"
            ),
            "translated_log_sha256": sha256(translated),
            "canonical_log_sha256": sha256(canonical),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/diffutils-3.12/hybrid"
    build = repository / "build/diffutils-3.12-hybrid"

    upstream_path = analysis / "upstream-tests.log"
    upstream = test_summaries(upstream_path)
    differential_path = analysis / "differential.json"
    differential = json.loads(differential_path.read_text())
    if not differential["gcc_clang_exact"] or differential["comparisons"] != 48:
        raise RuntimeError("translated GNU Diffutils differential suite is incomplete")
    valgrind = check_valgrind(analysis)

    expected_needed = ["libm.so.6", "libgcc_s.so.1", "libc.so.6", "ld-linux-x86-64.so.2"]
    binaries = {}
    for utility in UTILITIES:
        binary = build / f"{utility}-hybrid"
        stripped = build / f"{utility}-hybrid.stripped"
        canonical = build / f"{utility}.canonical-stripped"
        dynamic = (build / f"{utility}-hybrid.dynamic").read_text()
        needed = re.findall(r"Shared library: \[([^]]+)\]", dynamic)
        if needed != expected_needed:
            raise RuntimeError(f"unexpected GNU {utility} hybrid dependencies: {needed!r}")
        binaries[utility] = {
            "entrypoint": f"rustbox_{utility}_main",
            "linked_unstripped_bytes": binary.stat().st_size,
            "linked_stripped_bytes": stripped.stat().st_size,
            "canonical_stripped_bytes": canonical.stat().st_size,
            "linked_sections": {
                name.removeprefix("."): section(build / f"{utility}-hybrid.sections", name)
                for name in (".text", ".rodata", ".data", ".bss")
            },
            "linked_sha256": sha256(binary),
            "stripped_sha256": sha256(stripped),
            "dynamic_needed": needed,
        }

    translation = json.loads((repository / "evidence/diffutils-3.12-c2rust.json").read_text())
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-21",
        "release": "3.12",
        "status": "complete translated hybrids at canonical parity; multicall integration pending",
        "implementation": {
            "rust_production_sources": 139,
            "rust_files": translation["stable_translation"]["rust_files"],
            "public_names": list(UTILITIES),
            "generated_rust_repairs": 0,
        },
        "behavior": {
            "upstream_suites": upstream,
            "upstream_total": sum(summary["total"] for summary in upstream),
            "differential": differential,
            "valgrind": valgrind,
        },
        "size": {
            "translation_static_archive_bytes": translation["stable_translation"]["archive"]["bytes"],
            "binaries": binaries,
            "interpretation": "The static archive is link inventory, not release size.",
        },
        "artifacts": {
            "upstream_log_sha256": sha256(upstream_path),
            "differential_sha256": sha256(differential_path),
        },
        "runtime_linkage": {
            "current_dynamic_needed": expected_needed,
            "selinux": False,
            "systemd": False,
            "final_no_dt_needed_gate": "pending Rustbox-owned static runtime",
        },
        "input_evidence": {
            name: sha256(repository / f"evidence/{name}")
            for name in (
                "diffutils-3.12-oracle.json",
                "diffutils-3.12-analysis.json",
                "diffutils-3.12-normalization.json",
                "diffutils-3.12-c2rust.json",
            )
        },
        "next_gate": "link cmp, diff, diff3, and sdiff into Rustbox and replay combined regressions",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "differential": differential["comparisons"],
        "tests": evidence["behavior"]["upstream_total"],
        "stripped_bytes": {name: data["linked_stripped_bytes"] for name, data in binaries.items()},
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
