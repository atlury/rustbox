#!/usr/bin/env python3
"""Publish reproducible evidence for GNU bc's complete C2Rust translation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


ENTRYPOINTS = ("rustbox_bc_main", "rustbox_dc_main")
HOLES = {
    "compile_error_macros": re.compile(r"\bcompile_error!"),
    "todo_macros": re.compile(r"\btodo!"),
    "unimplemented_macros": re.compile(r"\bunimplemented!"),
    "panic_macros": re.compile(r"\bpanic!"),
}


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
        ["nm", "-g", "--defined-only", str(archive)],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout
    return sum(line.split()[-1:] == [symbol] for line in output.splitlines())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/bc-1.08.2"
    base = analysis / "translations/c2rust-0.22.1"
    raw = base / "bc-1.08.2-normalized-audit"
    stable = base / "bc-1.08.2-stable"
    database = analysis / "normalized/c2rust-compdb/compile_commands.json"
    normalization = repository / "evidence/bc-1.08.2-normalization.json"

    commands = json.loads(database.read_text())
    prefix = "/rustbox-bc/normalized-source/"
    sources = [str(record["file"]) for record in commands]
    if any(not source.startswith(prefix) for source in sources):
        raise RuntimeError("GNU bc C2Rust database escapes normalized source")
    production_sources = sorted({source.removeprefix(prefix) for source in sources})
    normalization_record = json.loads(normalization.read_text())
    expected_sources = json.loads(
        (repository / "evidence/bc-1.08.2-oracle.json").read_text()
    )["scope"]["production_sources"]
    if len(commands) != 21 or production_sources != expected_sources:
        raise RuntimeError("GNU bc C2Rust database is incomplete")
    if list(raw.rglob("*.c_decls.json")):
        raise RuntimeError("GNU bc unexpectedly emitted partial declaration maps")

    raw_check = json.loads((raw / "rustbox-cargo-check.json").read_text())
    stable_check = json.loads((stable / "rustbox-cargo-check.json").read_text())
    for label, check in (("raw", raw_check), ("stable", stable_check)):
        if not check["build_finished_success"] or check["errors"]:
            raise RuntimeError(f"{label} GNU bc Rust crate does not compile")
    if "nightly" not in raw_check["rustc"] or "rustc 1.99.0" not in stable_check["rustc"]:
        raise RuntimeError("GNU bc Rust toolchain evidence changed")

    raw_inventory = rust_inventory(raw)
    stable_inventory = rust_inventory(stable)
    if any(raw_inventory[name] for name in HOLES):
        raise RuntimeError("raw generated GNU bc Rust contains a translation hole")
    if any(stable_inventory[name] for name in HOLES):
        raise RuntimeError("stable GNU bc Rust contains a translation hole")

    archive = stable / "target/release/libbc_1_08_2_normalized_audit.a"
    exported = {
        symbol: exported_count(archive, symbol)
        for symbol in (*ENTRYPOINTS, "std_only", "out_of_memory", "rt_error", "rt_warn")
    }
    if any(count != 1 for count in exported.values()):
        raise RuntimeError(f"GNU bc stable archive exports are not unique: {exported}")

    modernization = json.loads((stable / "rustbox-modernization.json").read_text())
    expected_duplicates = [
        {"kept": "src/bc/util.rs", "mangled": "src/dc/numeric.rs", "symbol": "out_of_memory"},
        {"kept": "src/bc/util.rs", "mangled": "src/dc/numeric.rs", "symbol": "rt_error"},
        {"kept": "src/bc/util.rs", "mangled": "src/dc/numeric.rs", "symbol": "rt_warn"},
        {"kept": "src/bc/global.rs", "mangled": "src/dc/numeric.rs", "symbol": "std_only"},
    ]
    if len(modernization["changes"]) != 22 or modernization.get("duplicate_exports_mangled") != expected_duplicates:
        raise RuntimeError("GNU bc stable linkage modernization changed")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-21",
        "release": "1.08.2",
        "bundled_dc_release": "1.5.2",
        "status": "complete stable translation compiles without holes; hybrid parity pending",
        "input": {
            "normalization_evidence_sha256": sha256(normalization),
            "normalization_tree_sha256": normalization_record["normalization"]["normalized_tree_sha256"],
            "compile_database_sha256": sha256(database),
            "compile_commands": len(commands),
            "production_sources": production_sources,
        },
        "translator": {
            "name": "C2Rust",
            "version": "0.22.1",
            "fail_on_error": True,
            "preserve_unused_functions": True,
            "generated_rust_repairs": 0,
            "normalized_c_sources": 3,
            "declaration_map_emission": {
                "enabled": False,
                "reason": "all 21 units translate; C2Rust 0.22.1 then panics in optional foreign-item declaration-map metadata export",
                "partial_maps_accepted": False,
            },
        },
        "raw_translation": {
            **raw_inventory,
            "cargo_check": raw_check,
        },
        "stable_translation": {
            **stable_inventory,
            "cargo_check": stable_check,
            "modernization_manifest_sha256": sha256(stable / "rustbox-modernization.json"),
            "modernization": modernization,
            "archive": {
                "bytes": archive.stat().st_size,
                "sha256": sha256(archive),
                "exported_definition_counts": exported,
            },
        },
        "configuration": {
            "selinux": False,
            "systemd": False,
            "readline": False,
            "libedit": False,
        },
        "hardening": {
            "raw_pointers_and_unsafe_are_inventory_only": True,
            "later_order": [
                "eliminate raw pointers and unsafe",
                "replace std with Rustbox-owned no_std runtime",
            ],
        },
        "next_gate": "link the complete Rust archive and pass canonical GNU bc and dc differential tests",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "commands": len(commands),
        "entrypoints": sum(exported[symbol] for symbol in ENTRYPOINTS),
        "holes": sum(raw_inventory[name] for name in HOLES),
        "raw_pointers": stable_inventory["raw_pointer_type_occurrences"],
        "rust_files": stable_inventory["rust_files"],
        "rust_lines": stable_inventory["rust_lines"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
