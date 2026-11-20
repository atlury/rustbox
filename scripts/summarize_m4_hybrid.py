#!/usr/bin/env python3
"""Publish canonical-parity and size evidence for the GNU M4 hybrid."""

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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/m4-1.4.21/hybrid"
    build = repository / "build/m4-1.4.21-hybrid"
    binary = build / "m4"
    stripped = build / "m4.stripped"
    canonical_stripped = build / "m4.canonical-stripped"

    language = (analysis / "language-check.log").read_text(errors="replace")
    numbered = re.findall(r"^Checking .*/checks/(\d{3})\.", language, re.MULTILINE)
    if len(numbered) != 242 or len(set(numbered)) != 242:
        raise RuntimeError("hybrid M4 numbered language suite is incomplete")
    if "Checking /rustbox-m4/normalized-source/checks/stackovf.test" not in language:
        raise RuntimeError("M4 stack-overflow test is absent")
    if "\nPass\n" not in language or "All checks successful" not in language:
        raise RuntimeError("hybrid M4 language suite did not pass")
    skipped = set(re.findall(r"/checks/(1(?:2[89]|3[0-4]))\.changeword", language))
    if len(skipped) != 7:
        raise RuntimeError("M4 language policy skips changed")

    differential = json.loads((analysis / "differential.json").read_text())
    if not differential["canonical_hybrid_exact"] or differential["comparisons"] != 108:
        raise RuntimeError("hybrid M4 differential suite is incomplete")

    valgrind_path = analysis / "valgrind.log"
    valgrind = valgrind_path.read_text(errors="replace")
    if "ERROR SUMMARY: 0 errors" not in valgrind:
        raise RuntimeError("hybrid M4 Valgrind errors")
    for kind in ("definitely lost", "indirectly lost", "possibly lost"):
        if not re.search(rf"{kind}: 0 bytes in 0 blocks", valgrind):
            raise RuntimeError(f"hybrid M4 Valgrind reported {kind}")

    dynamic = (build / "m4.dynamic").read_text()
    needed = re.findall(r"Shared library: \[([^]]+)\]", dynamic)
    expected_needed = ["libm.so.6", "libgcc_s.so.1", "libc.so.6", "ld-linux-x86-64.so.2"]
    if needed != expected_needed:
        raise RuntimeError(f"unexpected hybrid M4 runtime dependencies: {needed!r}")

    evidence = {
        "schema": 1,
        "release": "1.4.21",
        "status": "translated hybrid at canonical parity; multicall integration pending",
        "implementation": {
            "rust_application_sources": 11,
            "normalized_gnulib_c_sources": 181,
            "entrypoint": "rustbox_m4_main",
        },
        "behavior": {
            "numbered_language_checks": len(numbered),
            "intentional_changeword_skips": len(skipped),
            "stack_overflow_check": "pass",
            "differential": differential,
            "valgrind": {
                "errors": 0,
                "definitely_indirectly_possibly_lost_bytes": 0,
                "reachable_process_lifetime_bytes": 531828,
            },
        },
        "size": {
            "translation_static_archive_bytes": json.loads(
                (repository / "evidence/m4-1.4.21-c2rust.json").read_text()
            )["stable_translation"]["archive"]["bytes"],
            "linked_unstripped_bytes": binary.stat().st_size,
            "linked_stripped_bytes": stripped.stat().st_size,
            "canonical_clang_stripped_bytes": canonical_stripped.stat().st_size,
            "linked_sections": {
                name.removeprefix("."): section(build / "m4.sections", name)
                for name in (".text", ".rodata", ".data", ".bss")
            },
            "interpretation": "The static archive is link inventory, not release size.",
        },
        "artifacts": {
            "linked_sha256": sha256(binary),
            "stripped_sha256": sha256(stripped),
            "language_log_sha256": sha256(analysis / "language-check.log"),
            "valgrind_log_sha256": sha256(valgrind_path),
        },
        "runtime_linkage": {
            "current_dynamic_needed": needed,
            "final_no_dt_needed_gate": "pending Rustbox-owned static runtime",
        },
        "input_evidence": {
            name: sha256(repository / f"evidence/{name}")
            for name in (
                "m4-1.4.21-oracle.json",
                "m4-1.4.21-normalization.json",
                "m4-1.4.21-c2rust.json",
            )
        },
        "next_gate": "link rustbox_m4_main into the single Rustbox multicall and replay all combined regressions",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "differential": differential["comparisons"],
        "language_checks": len(numbered),
        "stripped_bytes": stripped.stat().st_size,
        "text_bytes": evidence["size"]["linked_sections"]["text"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
