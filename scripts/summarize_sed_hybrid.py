#!/usr/bin/env python3
"""Publish canonical-parity and size evidence for translated GNU sed."""

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
        text, re.DOTALL,
    )
    names = ("total", "pass", "skip", "xfail", "fail", "xpass", "error")
    result = [dict(zip(names, map(int, values))) for values in matches]
    expected = [
        {"total": 75, "pass": 68, "skip": 7, "xfail": 0, "fail": 0, "xpass": 0, "error": 0},
        {"total": 287, "pass": 241, "skip": 46, "xfail": 0, "fail": 0, "xpass": 0, "error": 0},
    ]
    if result != expected:
        raise RuntimeError(f"translated GNU sed suite changed: {result}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/sed-4.10/hybrid"
    build = repository / "build/sed-4.10-hybrid"
    binary = build / "sed-hybrid"
    stripped = build / "sed-hybrid.stripped"
    canonical = build / "sed.canonical-stripped"

    upstream_path = analysis / "upstream-tests.log"
    upstream = test_summaries(upstream_path)
    differential_path = analysis / "differential.json"
    differential = json.loads(differential_path.read_text())
    if not differential["gcc_clang_exact"] or differential["comparisons"] != 30:
        raise RuntimeError("translated GNU sed differential suite is incomplete")

    valgrind_path = analysis / "valgrind.log"
    valgrind = valgrind_path.read_text(errors="replace")
    for phrase in (
        "ERROR SUMMARY: 0 errors",
        "definitely lost: 0 bytes in 0 blocks",
        "indirectly lost: 0 bytes in 0 blocks",
        "possibly lost: 0 bytes in 0 blocks",
        "still reachable: 4,317 bytes in 7 blocks",
    ):
        if phrase not in valgrind:
            raise RuntimeError("GNU sed hybrid Valgrind smoke failed")

    dynamic = (build / "sed-hybrid.dynamic").read_text()
    needed = re.findall(r"Shared library: \[([^]]+)\]", dynamic)
    expected_needed = [
        "libacl.so.1", "libattr.so.1", "libm.so.6", "libgcc_s.so.1",
        "libc.so.6", "ld-linux-x86-64.so.2",
    ]
    if needed != expected_needed:
        raise RuntimeError(f"unexpected GNU sed hybrid dependencies: {needed!r}")

    translation = json.loads((repository / "evidence/sed-4.10-c2rust.json").read_text())
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-20",
        "release": "4.10",
        "status": "complete translated hybrid at canonical parity; multicall integration pending",
        "implementation": {
            "rust_production_sources": 85,
            "rust_files": translation["stable_translation"]["rust_files"],
            "entrypoint": "rustbox_sed_main",
            "public_name": "sed",
            "generated_rust_repairs": 0,
            "abi_bridge": {
                "symbol": "__wctob_alias",
                "target": "wctob",
                "reason": "C2Rust preserves gnulib's C alias identifier but not its configured asm label",
            },
        },
        "behavior": {
            "upstream_suites": upstream,
            "upstream_total": sum(summary["total"] for summary in upstream),
            "differential": differential,
            "valgrind_smokes": 1,
            "valgrind_still_reachable_bytes": 4317,
        },
        "size": {
            "translation_static_archive_bytes": translation["stable_translation"]["archive"]["bytes"],
            "linked_unstripped_bytes": binary.stat().st_size,
            "linked_stripped_bytes": stripped.stat().st_size,
            "canonical_stripped_bytes": canonical.stat().st_size,
            "linked_sections": {
                name.removeprefix("."): section(build / "sed-hybrid.sections", name)
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
            "oracle_backends": ["libacl", "libattr"],
            "selinux": False,
            "systemd": False,
            "final_no_dt_needed_gate": "pending Rustbox-owned static runtime and ACL/xattr implementation",
        },
        "input_evidence": {
            name: sha256(repository / f"evidence/{name}")
            for name in (
                "sed-4.10-oracle.json",
                "sed-4.10-normalization.json",
                "sed-4.10-c2rust.json",
            )
        },
        "next_gate": "link sed into the single Rustbox multicall and replay combined regressions",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "differential": differential["comparisons"],
        "tests": evidence["behavior"]["upstream_total"],
        "stripped_bytes": stripped.stat().st_size,
        "text_bytes": evidence["size"]["linked_sections"]["text"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
