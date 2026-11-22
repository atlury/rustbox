#!/usr/bin/env python3
"""Publish reproducible evidence for GNU tar 1.35's complete C2Rust pass."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(crate: Path) -> dict[str, int]:
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
        "compile_error_macros": combined.count("compile_error!"),
        "todo_macros": combined.count("todo!"),
        "unimplemented_macros": combined.count("unimplemented!"),
        "c2rust_fallthrough_guards": combined.count(
            'panic!("Reached end of non-void function without returning")'
        ),
        "inline_assembly_occurrences": combined.count("asm!("),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/tar-1.35"
    base = analysis / "translations/c2rust-0.22.1"
    raw = base / "tar-1.35-normalized-audit"
    stable = base / "tar-1.35-stable"
    database = analysis / "normalized/c2rust-compdb/compile_commands.json"
    check_path = stable / "rustbox-cargo-check.json"
    modernization_path = stable / "rustbox-modernization.json"
    boundary_path = stable / "rustbox-tar-stable.json"

    commands = json.loads(database.read_text())
    if len(commands) != 197 or len({record["file"] for record in commands}) != 197:
        raise RuntimeError("GNU tar C2Rust command closure changed")
    if any(Path(record["file"]).suffix != ".c" for record in commands):
        raise RuntimeError("GNU tar C2Rust closure contains non-C input")

    check = json.loads(check_path.read_text())
    if not check["build_finished_success"] or check["errors"]:
        raise RuntimeError("stable GNU tar translation does not compile")
    if "rustc 1.99.0" not in check["rustc"]:
        raise RuntimeError("GNU tar stable toolchain changed")

    raw_inventory = inventory(raw)
    stable_inventory = inventory(stable)
    for label, values in (("raw", raw_inventory), ("stable", stable_inventory)):
        if values["rust_files"] != 199:
            raise RuntimeError(f"{label} GNU tar Rust inventory changed")
        if any(values[key] for key in (
            "compile_error_macros", "todo_macros", "unimplemented_macros",
            "inline_assembly_occurrences",
        )):
            raise RuntimeError(f"{label} GNU tar translation contains a hole")
        if values["c2rust_fallthrough_guards"] != 5:
            raise RuntimeError(f"{label} GNU tar fallthrough inventory changed")

    modernization = json.loads(modernization_path.read_text())
    boundary = json.loads(boundary_path.read_text())
    if sum(c.get("checked_arithmetic_rewrites", 0)
           for c in modernization["changes"]) != 80:
        raise RuntimeError("GNU tar checked-arithmetic modernization changed")
    if sum(c.get("integer_to_bool_rewrites", 0)
           for c in modernization["changes"]) != 17:
        raise RuntimeError("GNU tar integer-to-bool modernization changed")
    expected_residue = [
        "gnu/human.c", "gnu/printf-args.c", "gnu/printf-parse.c",
        "gnu/vasnprintf.c",
    ]
    if boundary["canonical_c_residue"] != expected_residue:
        raise RuntimeError("GNU tar canonical C ABI boundary changed")

    archive = stable / "target/release/libtar_1_35_normalized_audit.a"
    if not archive.is_file():
        raise RuntimeError("GNU tar stable archive is missing")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-22",
        "release": "1.35",
        "status": (
            "complete stable translation; four canonical C ABI units retained; "
            "hybrid parity is the next gate"
        ),
        "input": {
            "compile_commands": len(commands),
            "production_c_sources": 197,
            "compile_database_sha256": sha256(database),
        },
        "translator": {
            "name": "C2Rust",
            "version": "0.22.1",
            "fail_on_error": True,
            "preserve_unused_functions": True,
            "all_197_actions_translated": True,
            "compile_error_or_placeholder_holes": 0,
        },
        "raw_translation": raw_inventory,
        "stable_translation": {
            **stable_inventory,
            "cargo_check": check,
            "cargo_check_sha256": sha256(check_path),
            "modernization_manifest_sha256": sha256(modernization_path),
            "package_boundary_manifest_sha256": sha256(boundary_path),
            "checked_arithmetic_rewrites": 80,
            "integer_to_bool_rewrites": 17,
            "volatile_statement_terminator_rewrites": 1,
            "release_archive": {
                "bytes": archive.stat().st_size,
                "sha256": sha256(archive),
            },
        },
        "fallthrough_guard_audit": {
            "occurrences": 5,
            "semantic_holes": 0,
            "immediate_predecessors": {
                "wait_for_grandchild": 2,
                "xexec": 2,
                "fatal_exit": 1,
            },
            "basis": (
                "each generated guard immediately follows a canonical _Noreturn "
                "call and is reachable only if that upstream contract is violated"
            ),
        },
        "canonical_c_abi_residue": {
            "sources": expected_residue,
            "count": 4,
            "reason": boundary["residue_reason"],
            "translated_versions_retained_for_audit": True,
        },
        "dependencies": {
            "rust_crates": ["c2rust-bitfields", "f128", "num-traits", "libc"],
            "external_runtime_libraries": [],
        },
        "hardening": {
            "raw_pointers_and_unsafe_are_inventory_only": True,
            "later_order": [
                "eliminate raw pointers and unsafe",
                "replace std and Rust crates with Rustbox-owned no_std runtime",
            ],
        },
        "next_gate": "link and differentially verify tar and rmt hybrid entrypoints",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "actions": 197,
        "c_residue": 4,
        "holes": 0,
        "raw_pointers": stable_inventory["raw_pointer_type_occurrences"],
        "rust_files": stable_inventory["rust_files"],
        "rust_lines": stable_inventory["rust_lines"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
