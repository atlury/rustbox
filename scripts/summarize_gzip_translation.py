#!/usr/bin/env python3
"""Publish reproducible evidence for GNU Gzip's C2Rust translation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


ENTRYPOINT = "rustbox_gzip_main"
HOLES = {
    "compile_error_macros": re.compile(r"\bcompile_error!"),
    "todo_macros": re.compile(r"\btodo!"),
    "unimplemented_macros": re.compile(r"\bunimplemented!"),
    "panic_macros": re.compile(r"\bpanic!"),
}
EXCLUDED = [
    "lib/printf-args.c", "lib/printf-frexpl.c", "lib/printf-parse.c",
    "lib/vasnprintf.c",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rust_inventory(crate: Path) -> dict[str, object]:
    rust_files = sorted(crate.rglob("*.rs"))
    combined = "\n".join(path.read_text(encoding="utf-8") for path in rust_files)
    holes = {name: len(pattern.findall(combined)) for name, pattern in HOLES.items()}
    return {
        "rust_files": len(rust_files),
        "rust_lines": sum(path.read_text(encoding="utf-8").count("\n") for path in rust_files),
        "rust_bytes": sum(path.stat().st_size for path in rust_files),
        "file_sha256": {str(path.relative_to(crate)): sha256(path) for path in rust_files},
        **holes,
        "raw_pointer_type_occurrences": len(re.findall(r"\*(?:mut|const)\s+", combined)),
        "unsafe_function_occurrences": len(
            re.findall(r'\bunsafe\s+(?:extern\s+"C"\s+)?fn\b', combined)
        ),
        "unsafe_block_occurrences": len(re.findall(r"\bunsafe\s*\{", combined)),
    }


def exported_count(archive: Path, symbol: str) -> int:
    output = subprocess.run(
        ["nm", "-g", "--defined-only", str(archive)], check=True,
        stdout=subprocess.PIPE, text=True,
    ).stdout
    return sum(line.split()[-1:] == [symbol] for line in output.splitlines())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/gzip-1.14"
    base = analysis / "translations/c2rust-0.22.1"
    complete = base / "gzip-1.14-normalized-audit"
    reachable = base / "gzip-1.14-reachable-audit"
    stable = base / "gzip-1.14-stable"
    complete_database = analysis / "normalized/c2rust-compdb/compile_commands.json"
    reachable_database = analysis / "normalized/c2rust-reachable-compdb/compile_commands.json"
    normalization_path = repository / "evidence/gzip-1.14-normalization.json"

    complete_commands = json.loads(complete_database.read_text())
    reachable_commands = json.loads(reachable_database.read_text())
    if len(complete_commands) != 68 or len(reachable_commands) != 64:
        raise RuntimeError("GNU Gzip C2Rust command closure changed")
    complete_sources = {record["file"] for record in complete_commands}
    reachable_sources = {record["file"] for record in reachable_commands}
    excluded_paths = sorted(
        path.split("/normalized-source/", 1)[1]
        for path in complete_sources - reachable_sources
    )
    if excluded_paths != EXCLUDED:
        raise RuntimeError(f"GNU Gzip C2Rust exclusions changed: {excluded_paths}")

    complete_check = json.loads((complete / "rustbox-cargo-check.json").read_text())
    reachable_check = json.loads((reachable / "rustbox-cargo-check.json").read_text())
    stable_check = json.loads((stable / "rustbox-cargo-check.json").read_text())
    if complete_check["build_finished_success"]:
        raise RuntimeError("complete GNU Gzip audit unexpectedly accepted f128 variadics")
    actionable = [error for error in complete_check["errors"] if error.get("code")]
    if (
        len(actionable) != 1 or actionable[0]["code"] != "E0277"
        or "VaArgSafe" not in actionable[0]["message"]
    ):
        raise RuntimeError(f"complete GNU Gzip audit diagnostics changed: {actionable}")
    for label, check in (("reachable", reachable_check), ("stable", stable_check)):
        if not check["build_finished_success"] or check["errors"]:
            raise RuntimeError(f"{label} GNU Gzip Rust crate does not compile")
    if "nightly" not in reachable_check["rustc"] or "rustc 1.99.0" not in stable_check["rustc"]:
        raise RuntimeError("GNU Gzip Rust toolchain evidence changed")

    complete_inventory = rust_inventory(complete)
    reachable_inventory = rust_inventory(reachable)
    stable_inventory = rust_inventory(stable)
    for label, inventory in (
        ("complete", complete_inventory),
        ("reachable", reachable_inventory),
        ("stable", stable_inventory),
    ):
        if any(inventory[name] for name in HOLES):
            raise RuntimeError(f"{label} GNU Gzip Rust contains a translation hole")
    if (
        complete_inventory["rust_files"] != 70
        or reachable_inventory["rust_files"] != 66
        or stable_inventory["rust_files"] != 66
    ):
        raise RuntimeError("GNU Gzip Rust file inventory changed")
    if "f128" not in complete.joinpath("Cargo.toml").read_text():
        raise RuntimeError("complete GNU Gzip audit no longer records f128")
    if "f128" in reachable.joinpath("Cargo.toml").read_text() or "f128" in stable.joinpath("Cargo.toml").read_text():
        raise RuntimeError("reachable GNU Gzip crate retained f128")

    modernization_path = stable / "rustbox-modernization.json"
    modernization = json.loads(modernization_path.read_text())
    if len(modernization["changes"]) != 42:
        raise RuntimeError("GNU Gzip stable modernization changed")
    expected_duplicate = [{
        "kept": "src/normalized_source/lib/xalloc_die.rs",
        "mangled": "src/normalized_source/util.rs",
        "symbol": "xalloc_die",
    }]
    if modernization.get("duplicate_exports_mangled") != expected_duplicate:
        raise RuntimeError("GNU Gzip duplicate export mapping changed")

    archive = stable / "target/release/libgzip_1_14_reachable_audit.a"
    if exported_count(archive, ENTRYPOINT) != 1:
        raise RuntimeError("GNU Gzip stable archive entrypoint is not unique")
    normalization = json.loads(normalization_path.read_text())

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-21",
        "release": "1.14",
        "status": "complete stable reachable translation without holes; hybrid parity verified separately",
        "input": {
            "normalization_evidence_sha256": sha256(normalization_path),
            "normalization_tree_sha256": normalization["normalization"]["normalized_tree_sha256"],
            "complete_compile_database_sha256": sha256(complete_database),
            "reachable_compile_database_sha256": sha256(reachable_database),
            "complete_compile_commands": len(complete_commands),
            "reachable_compile_commands": len(reachable_commands),
        },
        "translator": {
            "name": "C2Rust",
            "version": "0.22.1",
            "fail_on_error": True,
            "preserve_unused_functions": True,
            "generated_rust_semantic_repairs": 0,
            "normalized_c_sources": 4,
            "complete_audit": {
                "all_68_sources_translated": True,
                "holes": 0,
                "compile_diagnostic": actionable[0],
                "reason": "C2Rust maps x86-64 C long double variadics to the f128 crate, which cannot implement Rust's sealed VaArgSafe ABI trait.",
            },
            "reachable_partition": {
                "rust_sources": 64,
                "excluded_sources": EXCLUDED,
                "canonical_c_bridge_sources": [
                    "lib/printf-args.c", "lib/printf-parse.c", "lib/vasnprintf.c",
                ],
                "unlinked_canonical_helper": "lib/printf-frexpl.c",
            },
        },
        "complete_translation": {**complete_inventory, "cargo_check": complete_check},
        "reachable_translation": {**reachable_inventory, "cargo_check": reachable_check},
        "stable_translation": {
            **stable_inventory,
            "cargo_check": stable_check,
            "modernization_manifest_sha256": sha256(modernization_path),
            "modernization": modernization,
            "archive": {
                "bytes": archive.stat().st_size,
                "sha256": sha256(archive),
                "entrypoint_definition_counts": {ENTRYPOINT: 1},
            },
        },
        "dependencies": {"rust_crates": ["libc"], "f128": False},
        "hardening": {
            "raw_pointers_and_unsafe_are_inventory_only": True,
            "later_order": [
                "eliminate raw pointers and unsafe",
                "replace std and libc crate use with Rustbox-owned no_std runtime",
            ],
        },
        "next_gate": "link the stable Rust archive with the three canonical variadic objects and retain all 14 names at canonical parity",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "complete_sources": 68,
        "holes": 0,
        "reachable_sources": 64,
        "raw_pointers": stable_inventory["raw_pointer_type_occurrences"],
        "rust_lines": stable_inventory["rust_lines"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
