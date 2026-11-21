#!/usr/bin/env python3
"""Publish reproducible evidence for XZ Utils 5.8.4's C2Rust translation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rust_inventory(crate: Path) -> dict[str, object]:
    files = sorted(crate.rglob("*.rs"))
    texts = [path.read_text(encoding="utf-8") for path in files]
    combined = "\n".join(texts)
    fallthroughs = combined.count(
        'panic!("Reached end of non-void function without returning")'
    )
    return {
        "rust_files": len(files),
        "rust_lines": sum(text.count("\n") for text in texts),
        "rust_bytes": sum(path.stat().st_size for path in files),
        "raw_pointer_type_occurrences": len(
            re.findall(r"\*(?:mut|const)\s+", combined)
        ),
        "unsafe_function_occurrences": len(
            re.findall(r'\bunsafe\s+(?:extern\s+"C"\s+)?fn\b', combined)
        ),
        "compile_error_macros": combined.count("compile_error!"),
        "todo_macros": combined.count("todo!"),
        "unimplemented_macros": combined.count("unimplemented!"),
        "unreachable_c_fallthrough_panics": fallthroughs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/xz-5.8.4"
    base = analysis / "translations/c2rust-0.22.1"
    raw = base / "xz-5.8.4-normalized-audit"
    stable = base / "xz-5.8.4-stable"
    database = analysis / "normalized/c2rust-compdb/compile_commands.json"
    raw_check_path = raw / "rustbox-cargo-check.json"
    stable_check_path = stable / "rustbox-cargo-check.json"
    modernization_path = stable / "rustbox-modernization.json"
    repairs_path = stable / "rustbox-xz-repairs.json"
    portable_path = (
        analysis / "translation-portable/canonical-normalized-differential.json"
    )

    commands = json.loads(database.read_text())
    if len(commands) != 102 or len({record["file"] for record in commands}) != 102:
        raise RuntimeError("XZ C2Rust command closure changed")
    raw_check = json.loads(raw_check_path.read_text())
    stable_check = json.loads(stable_check_path.read_text())
    if raw_check["build_finished_success"] or raw_check["diagnostics_by_level"]["error"] != 488:
        raise RuntimeError("XZ raw C2Rust diagnostic baseline changed")
    codes: dict[str, int] = {}
    for diagnostic in raw_check["errors"]:
        code = diagnostic.get("code")
        if code:
            codes[code] = codes.get(code, 0) + 1
    if codes != {"E0054": 4, "E0308": 480, "E0425": 2, "E0530": 1}:
        raise RuntimeError(f"XZ raw C2Rust repair classes changed: {codes}")
    if not stable_check["build_finished_success"] or stable_check["errors"]:
        raise RuntimeError("stable XZ translation does not compile")
    if "rustc 1.99.0" not in stable_check["rustc"]:
        raise RuntimeError("XZ stable Rust toolchain changed")

    raw_inventory = rust_inventory(raw)
    stable_inventory = rust_inventory(stable)
    for label, inventory in (("raw", raw_inventory), ("stable", stable_inventory)):
        if inventory["rust_files"] != 104:
            raise RuntimeError(f"{label} XZ Rust file inventory changed")
        if any(inventory[key] for key in (
            "compile_error_macros", "todo_macros", "unimplemented_macros"
        )):
            raise RuntimeError(f"{label} XZ translation contains a hole")
        if inventory["unreachable_c_fallthrough_panics"] != 5:
            raise RuntimeError(f"{label} XZ C fallthrough inventory changed")

    modernization = json.loads(modernization_path.read_text())
    if len(modernization["changes"]) != 28:
        raise RuntimeError("XZ stable modernization changed")
    repairs = json.loads(repairs_path.read_text())
    totals: dict[str, int] = {}
    for repair in repairs["repairs"]:
        for key, value in repair.items():
            if key.endswith("_repairs") or key.endswith("_casts"):
                totals[key] = totals.get(key, 0) + int(value)
    expected_totals = {
        "const_void_pointer_casts": 237,
        "mut_void_pointer_casts": 237,
        "integer_to_bool_repairs": 4,
        "size_arithmetic_repairs": 5,
    }
    if totals != expected_totals or len(repairs["repairs"]) != 85:
        raise RuntimeError(f"XZ deterministic repair manifest changed: {totals}")

    portable = json.loads(portable_path.read_text())
    if portable["cases"] != 70 or portable["passed"] != 70:
        raise RuntimeError("XZ translation-source parity changed")
    archive = stable / "target/release/libxz_5_8_4_normalized_audit.a"
    if not archive.is_file():
        raise RuntimeError("XZ stable release archive is missing")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-22",
        "release": "5.8.4",
        "status": "complete stable translation without holes; multicall integration next",
        "input": {
            "compile_commands": len(commands),
            "production_sources": 101,
            "decoder_personalities": 2,
            "compile_database_sha256": sha256(database),
            "portable_source_differential": {
                "cases": portable["cases"],
                "passed": portable["passed"],
                "sha256": sha256(portable_path),
            },
        },
        "translator": {
            "name": "C2Rust",
            "version": "0.22.1",
            "fail_on_error": True,
            "preserve_unused_functions": True,
            "all_102_actions_translated": True,
            "holes": 0,
            "portable_configuration": [
                "upstream pure-C CRC",
                "upstream pure-C range decoder",
                "omit optional x86 immintrin implementation",
                "omit one optional Clang vectorization hint",
            ],
        },
        "raw_translation": {
            **raw_inventory,
            "cargo_check_sha256": sha256(raw_check_path),
            "compiler_repair_classes": codes,
        },
        "stable_translation": {
            **stable_inventory,
            "cargo_check": stable_check,
            "modernization_changes": len(modernization["changes"]),
            "modernization_manifest_sha256": sha256(modernization_path),
            "repair_records": len(repairs["repairs"]),
            "repair_totals": totals,
            "repair_manifest_sha256": sha256(repairs_path),
            "release_archive": {
                "bytes": archive.stat().st_size,
                "sha256": sha256(archive),
            },
        },
        "dependencies": {"rust_crates": ["libc"]},
        "hardening": {
            "raw_pointers_and_unsafe_are_inventory_only": True,
            "later_order": [
                "eliminate raw pointers and unsafe",
                "replace std and libc crate use with Rustbox-owned no_std runtime",
            ],
        },
        "next_gate": "integrate all 23 XZ command and compatibility names into rustbox",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "actions": len(commands),
        "holes": 0,
        "raw_pointers": stable_inventory["raw_pointer_type_occurrences"],
        "rust_files": stable_inventory["rust_files"],
        "rust_lines": stable_inventory["rust_lines"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
