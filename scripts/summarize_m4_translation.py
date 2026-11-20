#!/usr/bin/env python3
"""Publish reproducible evidence for GNU M4's complete C2Rust translation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


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
        "file_sha256": {
            str(path.relative_to(crate)): sha256(path) for path in rust_files
        },
        **holes,
        "raw_pointer_type_occurrences": len(re.findall(r"\*(?:mut|const)\s+", combined)),
        "unsafe_function_occurrences": len(
            re.findall(r'\bunsafe\s+(?:extern\s+"C"\s+)?fn\b', combined)
        ),
        "unsafe_block_occurrences": len(re.findall(r"\bunsafe\s*\{", combined)),
    }


def exported_count(archive: Path, symbol: str) -> int:
    output = subprocess.run(
        ["nm", "-g", "--defined-only", archive],
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
    analysis = repository / "work/analysis/m4-1.4.21"
    base = analysis / "translations/c2rust-0.22.1"
    raw = base / "m4-1.4.21-normalized-audit"
    stable = base / "m4-1.4.21-stable"
    database = analysis / "normalized/c2rust-compdb/compile_commands.json"
    normalization = repository / "evidence/m4-1.4.21-normalization.json"

    commands = json.loads(database.read_text())
    names = sorted(Path(record["file"]).name for record in commands)
    if len(commands) != 11 or len(set(names)) != 11:
        raise RuntimeError("M4 C2Rust database is incomplete")
    declaration_maps = sorted(raw.glob("src/*.c_decls.json"))
    if len(declaration_maps) != 11:
        raise RuntimeError("M4 declaration maps are incomplete")

    raw_check = json.loads((raw / "rustbox-cargo-check.json").read_text())
    stable_check = json.loads((stable / "rustbox-cargo-check.json").read_text())
    for label, check in (("raw", raw_check), ("stable", stable_check)):
        if not check["build_finished_success"] or check["errors"]:
            raise RuntimeError(f"{label} M4 Rust crate does not compile")

    raw_inventory = rust_inventory(raw)
    stable_inventory = rust_inventory(stable)
    if any(raw_inventory[name] for name in HOLES):
        raise RuntimeError("raw generated M4 Rust contains a translation hole")
    if any(stable_inventory[name] for name in HOLES):
        raise RuntimeError("stable M4 Rust contains a translation hole")

    raw_archive = raw / "target/release/libm4_1_4_21_normalized_audit.a"
    stable_archive = stable / "target/release/libm4_1_4_21_normalized_audit.a"
    entry = "rustbox_m4_main"
    if exported_count(raw_archive, entry) != 1 or exported_count(stable_archive, entry) != 1:
        raise RuntimeError("M4 multicall entrypoint is not exported exactly once")

    modernization = json.loads((stable / "rustbox-modernization.json").read_text())
    evidence = {
        "schema": 1,
        "release": "1.4.21",
        "status": "complete stable translation compiles without holes; hybrid parity pending",
        "input": {
            "normalization_evidence_sha256": sha256(normalization),
            "compile_database_sha256": sha256(database),
            "compile_commands": len(commands),
            "production_sources": names,
        },
        "translator": {
            "name": "C2Rust",
            "version": "0.22.1",
            "fail_on_error": True,
            "preserve_unused_functions": True,
            "generated_rust_repairs": 0,
            "reason_for_direct_flags": (
                "C2Rust 0.22.1 misroutes a Bear JSON filename through ClangTool's "
                "directory-only -p interface, so the selected compile database is "
                "hashed and its common verified flags are passed directly."
            ),
        },
        "raw_translation": {
            **raw_inventory,
            "declaration_maps": len(declaration_maps),
            "declaration_map_sha256": {
                str(path.relative_to(raw)): sha256(path) for path in declaration_maps
            },
            "cargo_check": raw_check,
            "archive": {
                "bytes": raw_archive.stat().st_size,
                "sha256": sha256(raw_archive),
                "entrypoint": entry,
                "entrypoint_definitions": 1,
            },
        },
        "stable_translation": {
            **stable_inventory,
            "cargo_check": stable_check,
            "modernization_manifest_sha256": sha256(stable / "rustbox-modernization.json"),
            "modernization": modernization,
            "archive": {
                "bytes": stable_archive.stat().st_size,
                "sha256": sha256(stable_archive),
                "entrypoint": entry,
                "entrypoint_definitions": 1,
            },
        },
        "hardening": {
            "raw_pointers_and_unsafe_are_inventory_only": True,
            "later_order": ["eliminate raw pointers and unsafe", "replace std with Rustbox-owned no_std runtime"],
        },
        "next_gate": "link normalized gnulib support and pass canonical M4 differential tests",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "commands": len(commands),
        "holes": sum(raw_inventory[name] for name in HOLES),
        "raw_pointers": stable_inventory["raw_pointer_type_occurrences"],
        "rust_files": stable_inventory["rust_files"],
        "rust_lines": stable_inventory["rust_lines"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
