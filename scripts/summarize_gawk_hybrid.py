#!/usr/bin/env python3
"""Publish runnable-core parity evidence for translated GNU Gawk."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/gawk-5.4.0-hybrid"
ANALYSIS = ROOT / "work/analysis/gawk-5.4.0/hybrid"
TRANSLATIONS = ROOT / "work/analysis/gawk-5.4.0/translations/c2rust-0.22.1"
CORE = TRANSLATIONS / "gawk-5.4.0-core-stable"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def section(path: Path, name: str) -> int:
    match = re.search(rf"^{re.escape(name)}\s+(\d+)\s+", path.read_text(), re.MULTILINE)
    if match is None:
        raise RuntimeError(f"missing {name} in {path}")
    return int(match.group(1))


def main() -> int:
    combination_path = CORE / "rustbox-combination.json"
    modernization_path = CORE / "rustbox-modernization.json"
    combination = json.loads(combination_path.read_text())
    modernization = json.loads(modernization_path.read_text())
    if (combination["scope"], combination["modules"],
            combination["declaration_maps"]) != ("core", 38, 36):
        raise RuntimeError("GNU Gawk core translation surface changed")
    if modernization["stable_toolchain"] != "1.99.0":
        raise RuntimeError("GNU Gawk core stable toolchain changed")

    release_log = (TRANSLATIONS / "core-cargo-release.log").read_text(errors="replace")
    if (len(re.findall(r"Finished `release` profile", release_log)) != 1 or
            len(re.findall(r"(?m)^error(?:\[|:)", release_log)) != 0 or
            re.findall(r"generated (\d+) warnings", release_log) != ["627"]):
        raise RuntimeError("GNU Gawk core release build changed")

    differential_path = ANALYSIS / "differential.json"
    differential = json.loads(differential_path.read_text())
    if differential["cases"] != 26 or differential["passed"] != 26:
        raise RuntimeError("GNU Gawk translated differential changed")
    valgrind = {}
    for implementation in ("canonical", "hybrid"):
        path = ANALYSIS / f"valgrind-{implementation}.log"
        text = path.read_text(errors="replace")
        expected = (
            "definitely lost: 0 bytes",
            "indirectly lost: 0 bytes",
            "possibly lost: 0 bytes",
            "ERROR SUMMARY: 0 errors",
        )
        if not all(item in text for item in expected):
            raise RuntimeError(f"GNU Gawk {implementation} Valgrind result changed")
        valgrind[implementation] = sha256(path)

    binary = BUILD / "gawk"
    stripped = BUILD / "gawk.stripped"
    canonical = BUILD / "gawk.canonical-stripped"
    archive = CORE / "target/release/libgawk_5_4_0_core.a"
    dynamic = (BUILD / "gawk.dynamic").read_text()
    needed = re.findall(r"Shared library: \[([^]]+)\]", dynamic)
    expected_needed = [
        "libreadline.so.8", "libmpfr.so.6", "libgmp.so.10", "libm.so.6",
        "libgcc_s.so.1", "libc.so.6", "ld-linux-x86-64.so.2",
    ]
    if needed != expected_needed:
        raise RuntimeError(f"unexpected GNU Gawk hybrid dependencies: {needed!r}")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-22",
        "release": "5.4.0",
        "status": "runnable translated core at public differential parity; full upstream suite pending",
        "implementation": {
            "core_rust_modules": combination["modules"],
            "separate_translated_modules": 17,
            "entrypoint": "rustbox_gawk_main",
            "generated_rust_repairs": 0,
            "abi_wrappers": {"__btowc_alias": "btowc", "__wctob_alias": "wctob"},
            "extension_architecture": "separate shared objects, matching canonical GNU Gawk",
        },
        "behavior": {
            "differential": {"cases": 26, "passed": 26},
            "canonical_extension_loaded": "ordchr.so",
            "valgrind_zero_errors_and_leaks": True,
            "valgrind_log_sha256": valgrind,
        },
        "size": {
            "translation_static_archive_bytes": archive.stat().st_size,
            "linked_unstripped_bytes": binary.stat().st_size,
            "linked_stripped_bytes": stripped.stat().st_size,
            "canonical_stripped_bytes": canonical.stat().st_size,
            "linked_sections": {
                name.removeprefix("."): section(BUILD / "gawk.sections", name)
                for name in (".text", ".rodata", ".data", ".bss")
            },
            "interpretation": "The static archive is link inventory, not release size.",
        },
        "runtime_linkage": {
            "current_dynamic_needed": needed,
            "selinux": False,
            "systemd": False,
            "final_no_dt_needed_gate": "pending Rustbox-owned static runtime integration",
        },
        "artifacts": {
            "combination_manifest_sha256": sha256(combination_path),
            "modernization_manifest_sha256": sha256(modernization_path),
            "core_release_log_sha256": sha256(TRANSLATIONS / "core-cargo-release.log"),
            "differential_sha256": sha256(differential_path),
            "linked_sha256": sha256(binary),
            "stripped_sha256": sha256(stripped),
        },
        "next_gate": "substitute the translated core into the complete canonical GNU Gawk test suite",
    }
    output = ROOT / "evidence/gawk-5.4.0-hybrid.json"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "differential": 26,
        "rust_modules": combination["modules"],
        "stripped_bytes": stripped.stat().st_size,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
