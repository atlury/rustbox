#!/usr/bin/env python3
"""Publish reproducible evidence for pkgconf's complete C2Rust translation."""

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
ENTRYPOINTS = (
    "rustbox_pkgconf_main",
    "rustbox_bomtool_main",
    "rustbox_pccritic_main",
    "rustbox_spdxtool_main",
)


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
    analysis = repository / "work/analysis/pkgconf-3.0.11"
    base = analysis / "translations/c2rust-0.22.1"
    raw = base / "pkgconf-3.0.11-normalized-audit"
    stable = base / "pkgconf-3.0.11-stable"
    database = analysis / "normalized/c2rust-compdb/compile_commands.json"
    normalization = repository / "evidence/pkgconf-3.0.11-normalization.json"

    commands = json.loads(database.read_text())
    sources = sorted({record["file"] for record in commands})
    if len(commands) != 35 or len(sources) != 35:
        raise RuntimeError("pkgconf C2Rust database is incomplete")
    declaration_maps = sorted(raw.rglob("*.c_decls.json"))
    if len(declaration_maps) != 35:
        raise RuntimeError("pkgconf declaration maps are incomplete")

    raw_check = json.loads((raw / "rustbox-cargo-check.json").read_text())
    stable_check = json.loads((stable / "rustbox-cargo-check.json").read_text())
    for label, check in (("raw", raw_check), ("stable", stable_check)):
        if not check["build_finished_success"] or check["errors"]:
            raise RuntimeError(f"{label} pkgconf Rust crate does not compile")

    raw_inventory = rust_inventory(raw)
    stable_inventory = rust_inventory(stable)
    if any(raw_inventory[name] for name in HOLES):
        raise RuntimeError("raw generated pkgconf Rust contains a translation hole")
    if any(stable_inventory[name] for name in HOLES):
        raise RuntimeError("stable pkgconf Rust contains a translation hole")

    stable_archive = stable / "target/release/libpkgconf_3_0_11_normalized_audit.a"
    definitions = {symbol: exported_count(stable_archive, symbol) for symbol in ENTRYPOINTS}
    if set(definitions.values()) != {1}:
        raise RuntimeError(f"pkgconf multicall entrypoints are not unique: {definitions}")

    modernization = json.loads((stable / "rustbox-modernization.json").read_text())
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-20",
        "release": "3.0.11",
        "status": "complete stable translation compiles without holes; hybrid parity pending",
        "input": {
            "normalization_evidence_sha256": sha256(normalization),
            "compile_database_sha256": sha256(database),
            "compile_commands": len(commands),
            "production_sources": [
                Path(source).relative_to("/rustbox-pkgconf/normalized-source").as_posix()
                for source in sources
            ],
        },
        "translator": {
            "name": "C2Rust",
            "version": "0.22.1",
            "fail_on_error": True,
            "preserve_unused_functions": True,
            "generated_rust_repairs": 0,
            "translation_compatibility_c_rewrites": 1,
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
        },
        "stable_translation": {
            **stable_inventory,
            "cargo_check": stable_check,
            "modernization_manifest_sha256": sha256(stable / "rustbox-modernization.json"),
            "modernization": modernization,
            "archive": {
                "bytes": stable_archive.stat().st_size,
                "sha256": sha256(stable_archive),
                "entrypoint_definitions": definitions,
            },
        },
        "hardening": {
            "raw_pointers_and_unsafe_are_inventory_only": True,
            "later_order": [
                "eliminate raw pointers and unsafe",
                "replace std with Rustbox-owned no_std runtime",
            ],
        },
        "next_gate": "link the complete Rust archive and pass canonical pkgconf differential tests",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "commands": len(commands),
                "entrypoints": len(definitions),
                "holes": sum(raw_inventory[name] for name in HOLES),
                "raw_pointers": stable_inventory["raw_pointer_type_occurrences"],
                "rust_files": stable_inventory["rust_files"],
                "rust_lines": stable_inventory["rust_lines"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
