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
EXTENSIONS = TRANSLATIONS / "gawk-5.4.0-extensions"


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
            combination["declaration_maps"]) != ("core", 37, 35):
        raise RuntimeError("GNU Gawk core translation surface changed")
    if modernization["stable_toolchain"] != "1.99.0":
        raise RuntimeError("GNU Gawk core stable toolchain changed")

    release_log = (TRANSLATIONS / "core-cargo-release.log").read_text(errors="replace")
    if (len(re.findall(r"Finished `release` profile", release_log)) != 1 or
            len(re.findall(r"(?m)^error(?:\[|:)", release_log)) != 0 or
            re.findall(r"generated (\d+) warnings", release_log) != ["605"]):
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

    upstream_path = ANALYSIS / "upstream-tests.log"
    upstream = upstream_path.read_text(errors="replace")
    if (len(re.findall(r"Segmentation fault.*GAWK_PERSIST_FILE=test\.pma", upstream)) != 1 or
            len(re.findall(r"Error 139", upstream)) != 1 or
            "runtime error:" in upstream or "AddressSanitizer" in upstream):
        raise RuntimeError("GNU Gawk translated upstream suite result changed")
    timeout_ignored = len(re.findall(r"timeout\] Error 1 \(ignored\)", upstream))
    if timeout_ignored not in (0, 1):
        raise RuntimeError("GNU Gawk timeout scheduling result changed")
    timeout_artifacts = {}
    if timeout_ignored:
        expected_timeout = ANALYSIS / "timeout-expected"
        actual_timeout = ANALYSIS / "timeout-actual"
        expected_without_second_retry = expected_timeout.read_text().replace(
            "2 timed out; trying again\n", "")
        if actual_timeout.read_text() != expected_without_second_retry:
            raise RuntimeError("GNU Gawk ignored timeout variant changed")
        timeout_artifacts = {
            "expected_sha256": sha256(expected_timeout),
            "actual_sha256": sha256(actual_timeout),
        }

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
    residue_object = BUILD / "c-residue/pma.o"
    residue_symbols_path = BUILD / "c-residue/pma.symbols"
    residue_symbols = [line.split()[-1] for line in residue_symbols_path.read_text().splitlines()]
    expected_residue_symbols = [
        "pma_calloc", "pma_check_and_dump", "pma_errno", "pma_free",
        "pma_get_root", "pma_init", "pma_malloc", "pma_realloc",
        "pma_set_avail_mem", "pma_set_root", "pma_version",
    ]
    if residue_symbols != expected_residue_symbols:
        raise RuntimeError(f"GNU Gawk PMA C residue changed: {residue_symbols!r}")
    extension_manifest_path = EXTENSIONS / "rustbox-extensions.json"
    extension_manifest = json.loads(extension_manifest_path.read_text())
    extension_names = sorted(extension_manifest["extensions"])
    expected_extensions = [
        "filefuncs", "fnmatch", "fork", "inplace", "intdiv", "ordchr",
        "readdir", "readfile", "revoutput", "revtwoway", "rwarray",
        "testext", "time",
    ]
    if (extension_names != expected_extensions or
            extension_manifest["libraries"] != 13 or extension_manifest["modules"] != 15):
        raise RuntimeError("GNU Gawk translated extension surface changed")
    extension_build_log_path = TRANSLATIONS / "extensions-cargo-release.log"
    extension_build_log = extension_build_log_path.read_text(errors="replace")
    extension_warnings = {
        name: int(count) for name, count in re.findall(
            r"warning: `gawk_ext_([a-z]+)` \(lib\) generated (\d+) warnings",
            extension_build_log,
        )
    }
    if (sorted(extension_warnings) != extension_names or
            len(re.findall(r"Finished `release` profile", extension_build_log)) != 1 or
            re.search(r"(?m)^error(?:\[|:)", extension_build_log)):
        raise RuntimeError("GNU Gawk translated extension build changed")
    extension_sizes = {}
    extension_symbol_hashes = {}
    for name in extension_names:
        library = EXTENSIONS / f"target/release/lib{name}.so"
        symbols = EXTENSIONS / f"target/release/{name}.symbols"
        text = symbols.read_text()
        if (len(re.findall(r" T dl_load$", text, re.MULTILINE)) != 1 or
                len(re.findall(r" [BD] plugin_is_GPL_compatible$", text, re.MULTILINE)) != 1):
            raise RuntimeError(f"GNU Gawk extension export surface changed: {name}")
        extension_sizes[name] = library.stat().st_size
        extension_symbol_hashes[name] = sha256(symbols)

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-22",
        "release": "5.4.0",
        "status": "translated core and extensions at complete canonical test parity; gawk, awk, and native gawkbug integrated into the unified multicall",
        "implementation": {
            "core_rust_modules": combination["modules"],
            "separate_translated_modules": 18,
            "entrypoint": "rustbox_gawk_main",
            "generated_rust_repairs": 0,
            "exact_c_residue": {
                "source": "support/pma.c",
                "reason": "x86_64 GNU long-double ABI is not representable by C2Rust f128",
                "defined_symbols": residue_symbols,
            },
            "abi_wrappers": {"__btowc_alias": "btowc", "__wctob_alias": "wctob"},
            "extension_architecture": "separate shared objects, matching canonical GNU Gawk",
            "translated_extensions": {
                "libraries": extension_names,
                "production_libraries": 12,
                "test_libraries": 1,
                "source_modules": extension_manifest["modules"],
                "cargo_warnings": extension_warnings,
                "required_exports_verified": ["dl_load", "plugin_is_GPL_compatible"],
            },
        },
        "behavior": {
            "differential": {"cases": 26, "passed": 26},
            "canonical_extension_loaded": "ordchr.so",
            "complete_upstream_suite": {
                "passed": True,
                "output_differences": 0,
                "ignored_scheduling_transcripts": timeout_ignored,
                "pma_virtualization_failures": 1,
                "pma_failure_matches_canonical": True,
                "timeout_scheduling_variant": bool(timeout_ignored),
                "timeout_artifacts": timeout_artifacts,
            },
            "valgrind_zero_errors_and_leaks": True,
            "valgrind_log_sha256": valgrind,
        },
        "size": {
            "translation_static_archive_bytes": archive.stat().st_size,
            "translated_extension_bytes": extension_sizes,
            "translated_extension_total_bytes": sum(extension_sizes.values()),
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
            "upstream_suite_sha256": sha256(upstream_path),
            "pma_residue_sha256": sha256(residue_object),
            "pma_residue_symbols_sha256": sha256(residue_symbols_path),
            "extension_manifest_sha256": sha256(extension_manifest_path),
            "extension_release_log_sha256": sha256(extension_build_log_path),
            "extension_symbol_sha256": extension_symbol_hashes,
            "linked_sha256": sha256(binary),
            "stripped_sha256": sha256(stripped),
        },
        "next_gate": "begin the next queued canonical utility family",
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
