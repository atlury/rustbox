#!/usr/bin/env python3
"""Publish reproducible evidence for Ncurses 6.6's complete C2Rust crate."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rust_inventory(crate: Path) -> dict[str, int]:
    files = sorted(crate.rglob("*.rs"))
    texts = [path.read_text(encoding="utf-8") for path in files]
    combined = "\n".join(texts)
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
        "unsafe_block_occurrences": len(re.findall(r"\bunsafe\s*\{", combined)),
        "compile_error_macros": combined.count("compile_error!"),
        "todo_macros": combined.count("todo!"),
        "unimplemented_macros": combined.count("unimplemented!"),
        "panic_macros": combined.count("panic!"),
    }


def rewrite_totals(modernization: dict[str, object]) -> dict[str, int]:
    names = (
        "va_list_impl_rewrites",
        "as_va_list_rewrites",
        "va_arg_rewrites",
        "integer_to_bool_rewrites",
        "write_volatile_semicolon_rewrites",
    )
    changes = modernization["changes"]
    assert isinstance(changes, list)
    return {
        name: sum(int(change.get(name, 0)) for change in changes)
        for name in names
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/ncurses-6.6"
    base = analysis / "translations/c2rust-0.22.1"
    raw = base / "ncurses-6.6-normalized-audit"
    stable = base / "ncurses-6.6-normalized-audit-stable"
    database = analysis / "normalized/c2rust-compdb/compile_commands.json"
    probe_path = analysis / "normalized/c2rust-probe/results.json"
    manifest_path = analysis / "normalization-manifest.json"
    normalization_path = repository / "evidence/ncurses-6.6-normalization.json"
    modernization_path = stable / "rustbox-modernization.json"
    check_path = stable / "rustbox-cargo-check.json"

    manifest = json.loads(manifest_path.read_text())
    if (len(manifest.get("changed_sources", [])), manifest.get("entrypoints")) != (9, 7):
        raise RuntimeError("Ncurses translation normalization changed")
    commands = json.loads(database.read_text())
    if len(commands) != 264 or len({record["file"] for record in commands}) != 264:
        raise RuntimeError("Ncurses combined translation closure changed")
    if not all("-DRUSTBOX_MULTICALL=1" in record["arguments"] for record in commands):
        raise RuntimeError("Ncurses combined translation lost the multicall define")
    probe = json.loads(probe_path.read_text())
    if (probe.get("commands"), probe.get("passed"), probe.get("failed")) != (264, 264, 0):
        raise RuntimeError("Ncurses strict translation probe is incomplete")
    if probe.get("normalization_manifest_sha256") != sha256(manifest_path):
        raise RuntimeError("Ncurses probe and combined translation normalization differ")

    raw_inventory = rust_inventory(raw)
    stable_inventory = rust_inventory(stable)
    for label, inventory in (("raw", raw_inventory), ("stable", stable_inventory)):
        if inventory["rust_files"] != 266:
            raise RuntimeError(f"{label} Ncurses Rust file inventory changed")
        for name in (
            "compile_error_macros", "todo_macros", "unimplemented_macros", "panic_macros"
        ):
            if inventory[name]:
                raise RuntimeError(f"{label} Ncurses translation contains {name}")

    modernization = json.loads(modernization_path.read_text())
    totals = rewrite_totals(modernization)
    expected_totals = {
        "as_va_list_rewrites": 287,
        "integer_to_bool_rewrites": 14,
        "va_arg_rewrites": 15,
        "va_list_impl_rewrites": 73,
        "write_volatile_semicolon_rewrites": 1,
    }
    duplicates = modernization.get("duplicate_exports_mangled", [])
    if len(modernization["changes"]) != 265 or totals != expected_totals:
        raise RuntimeError(f"Ncurses reusable stable modernization changed: {totals}")
    if duplicates:
        raise RuntimeError("Ncurses shared program-global linkage regressed")

    check = json.loads(check_path.read_text())
    if not check["build_finished_success"] or check["exit_status"] or check["errors"]:
        raise RuntimeError("complete Ncurses translation does not compile on stable Rust")
    if "rustc 1.99.0" not in check["rustc"]:
        raise RuntimeError("Ncurses stable Rust toolchain changed")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-22",
        "release": "6.6",
        "status": "complete stable translation compiles without holes; hybrid parity next",
        "input": {
            "normalization_evidence_sha256": sha256(normalization_path),
            "normalization_manifest_sha256": sha256(manifest_path),
            "compile_database_sha256": sha256(database),
            "compile_commands": 264,
            "production_sources": 264,
            "native_public_names": 10,
        },
        "translator": {
            "name": "C2Rust",
            "version": "0.22.1",
            "fail_on_error": True,
            "preserve_unused_functions": True,
            "strict_unit_probe": {
                "commands": 264,
                "passed": 264,
                "failed": 0,
                "seconds": probe["seconds"],
                "sha256": sha256(probe_path),
            },
            "combined_translation": True,
            "holes": 0,
            "ncurses_specific_generated_rust_repairs": 0,
        },
        "raw_translation": raw_inventory,
        "stable_translation": {
            **stable_inventory,
            "cargo_check": check,
            "cargo_check_sha256": sha256(check_path),
            "modernization_changes": len(modernization["changes"]),
            "modernization_rewrite_totals": totals,
            "duplicate_program_globals_mangled": duplicates,
            "one_shared_multicall_progname_definition": True,
            "modernization_manifest_sha256": sha256(modernization_path),
        },
        "dependencies": {"rust_crates": ["c2rust-bitfields", "libc"]},
        "hardening": {
            "raw_pointers_and_unsafe_are_inventory_only": True,
            "later_order": [
                "pass canonical C/Rust hybrid differential tests",
                "integrate the ten native personalities into rustbox",
                "eliminate raw pointers and unsafe",
                "replace std and libc crate use with Rustbox-owned no_std runtime",
            ],
        },
        "next_gate": "build the stable archive and link canonical C ABI residue only where required for hybrid parity",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "commands": 264,
        "holes": 0,
        "raw_pointers": stable_inventory["raw_pointer_type_occurrences"],
        "rust_files": stable_inventory["rust_files"],
        "rust_lines": stable_inventory["rust_lines"],
        "stable_errors": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
