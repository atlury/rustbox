#!/usr/bin/env python3
"""Publish reproducible evidence for zstd 1.5.7's complete C2Rust pass."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(crate: Path) -> dict[str, object]:
    files = sorted(crate.rglob("*.rs"))
    texts = [path.read_text(encoding="utf-8") for path in files]
    combined = "\n".join(texts)
    return {
        "rust_files": len(files),
        "rust_lines": sum(text.count("\n") for text in texts),
        "rust_bytes": sum(path.stat().st_size for path in files),
        "raw_pointer_type_occurrences": len(re.findall(r"\*(?:mut|const)\s+", combined)),
        "unsafe_function_occurrences": len(
            re.findall(r'\bunsafe\s+(?:extern\s+"C"\s+)?fn\b', combined)
        ),
        "compile_error_macros": combined.count("compile_error!"),
        "todo_macros": combined.count("todo!"),
        "unimplemented_macros": combined.count("unimplemented!"),
        "unreachable_c_fallthrough_panics": combined.count(
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
    analysis = repository / "work/analysis/zstd-1.5.7"
    base = analysis / "translations/c2rust-0.22.1"
    raw = base / "zstd-1.5.7-normalized-audit"
    stable = base / "zstd-1.5.7-stable"
    database = analysis / "normalized/c2rust-compdb/compile_commands.json"
    portable_path = analysis / "translation-portable/canonical-normalized-differential.json"
    check_path = stable / "rustbox-cargo-check.json"
    modernization_path = stable / "rustbox-modernization.json"

    commands = json.loads(database.read_text())
    if len(commands) != 44 or len({record["file"] for record in commands}) != 44:
        raise RuntimeError("zstd C2Rust command closure changed")
    if any(Path(record["file"]).suffix != ".c" for record in commands):
        raise RuntimeError("zstd C2Rust closure contains non-C input")
    required_flags = {
        "-DRUSTBOX_MULTICALL=1", "-DDYNAMIC_BMI2=0",
        "-DZSTD_NO_INTRINSICS=1", "-DXXH_VECTOR=0", "-DXXH_DEBUGLEVEL=1",
    }
    if any(not required_flags.issubset(record["arguments"]) for record in commands):
        raise RuntimeError("zstd portable translation flags changed")

    portable = json.loads(portable_path.read_text())
    if portable.get("cases") != 17 or portable.get("passed") != 17:
        raise RuntimeError("zstd translation-source differential changed")
    check = json.loads(check_path.read_text())
    if not check["build_finished_success"] or check["errors"]:
        raise RuntimeError("stable zstd translation does not compile")
    if "rustc 1.99.0" not in check["rustc"]:
        raise RuntimeError("zstd stable toolchain changed")

    raw_inventory = inventory(raw)
    stable_inventory = inventory(stable)
    for label, values in (("raw", raw_inventory), ("stable", stable_inventory)):
        if values["rust_files"] != 46:
            raise RuntimeError(f"{label} zstd Rust inventory changed")
        if any(values[key] for key in (
            "compile_error_macros", "todo_macros", "unimplemented_macros",
            "unreachable_c_fallthrough_panics",
        )):
            raise RuntimeError(f"{label} zstd translation contains a hole")
    if stable_inventory["inline_assembly_occurrences"] != 14:
        raise RuntimeError("zstd translated assembly inventory changed")

    modernization = json.loads(modernization_path.read_text())
    if len(modernization["changes"]) != 21:
        raise RuntimeError("zstd stable modernization changed")
    archive = stable / "target/release/libzstd_1_5_7_normalized_audit.a"
    if not archive.is_file():
        raise RuntimeError("zstd stable archive is missing")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-22",
        "release": "1.5.7",
        "status": "complete stable translation without holes; hybrid parity verified separately",
        "input": {
            "compile_commands": len(commands),
            "production_c_sources": 44,
            "compile_database_sha256": sha256(database),
            "portable_source_differential": {
                "cases": 17,
                "passed": 17,
                "sha256": sha256(portable_path),
            },
        },
        "translator": {
            "name": "C2Rust",
            "version": "0.22.1",
            "fail_on_error": True,
            "preserve_unused_functions": True,
            "all_44_actions_translated": True,
            "holes": 0,
            "portable_configuration": [
                "upstream pure-C Huffman decoder",
                "disable runtime BMI2 and compiler intrinsics",
                "scalar xxHash with checked assertions",
                "constant zero CPUID because runtime BMI2 is disabled",
                "equivalent C address selection instead of x86 cmova",
            ],
        },
        "raw_translation": raw_inventory,
        "stable_translation": {
            **stable_inventory,
            "cargo_check": check,
            "cargo_check_sha256": sha256(check_path),
            "modernization_changes": len(modernization["changes"]),
            "modernization_manifest_sha256": sha256(modernization_path),
            "release_archive": {
                "bytes": archive.stat().st_size,
                "sha256": sha256(archive),
            },
        },
        "assembly_review": {
            "occurrences": 14,
            "semantic_algorithm_assembly": False,
            "classes": [
                "upstream loop-alignment directives",
                "upstream no-op padding directives",
                "one upstream compiler-ordering barrier",
            ],
            "decision": "retain and inventory the ordering barrier instead of weakening canonical semantics",
        },
        "dependencies": {"rust_crates": ["libc"]},
        "hardening": {
            "raw_pointers_and_unsafe_are_inventory_only": True,
            "later_order": [
                "eliminate raw pointers and unsafe",
                "replace std and libc crate use with Rustbox-owned no_std runtime",
            ],
        },
        "next_gate": "integrate all six zstd command names into rustbox",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "actions": 44,
        "holes": 0,
        "raw_pointers": stable_inventory["raw_pointer_type_occurrences"],
        "rust_files": stable_inventory["rust_files"],
        "rust_lines": stable_inventory["rust_lines"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
