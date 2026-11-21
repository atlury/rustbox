#!/usr/bin/env python3
"""Publish reproducible evidence for Less 710's complete C2Rust translation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


HOLES = ("compile_error", "todo", "unimplemented", "panic")
ENTRYPOINTS = ("rustbox_less_main", "rustbox_lessecho_main")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(crate: Path) -> dict[str, object]:
    files = sorted(crate.rglob("*.rs"))
    text = "\n".join(path.read_text(encoding="utf-8") for path in files)
    return {
        "rust_files": len(files),
        "rust_lines": sum(path.read_text(encoding="utf-8").count("\n") for path in files),
        "rust_bytes": sum(path.stat().st_size for path in files),
        "raw_pointer_type_occurrences": len(re.findall(r"\*(?:mut|const)\s+", text)),
        "unsafe_function_occurrences": len(
            re.findall(r'\bunsafe\s+(?:extern\s+"C"\s+)?fn\b', text)
        ),
        "holes": {name: len(re.findall(rf"\b{name}!", text)) for name in HOLES},
    }


def symbol_count(archive: Path, symbol: str) -> int:
    output = subprocess.run(
        ["nm", "-g", "--defined-only", str(archive)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    return sum(line.split()[-1:] == [symbol] for line in output.splitlines())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/less-710"
    base = analysis / "translations/c2rust-0.22.1"
    raw = base / "less-710-normalized-audit"
    stable = base / "less-710-stable"
    database = analysis / "normalized/c2rust-compdb/compile_commands.json"
    commands = json.loads(database.read_text())
    sources = sorted(Path(record["file"]).name for record in commands)
    if len(commands) != 38 or len(set(sources)) != 38:
        raise RuntimeError("Less C2Rust closure is incomplete")
    if any("-DRUSTBOX_MULTICALL=1" not in record["arguments"] for record in commands):
        raise RuntimeError("Less C2Rust closure lost the normalized entrypoint define")
    declaration_maps = sorted(raw.glob("src/*.c_decls.json"))
    if len(declaration_maps) != 38:
        raise RuntimeError("Less declaration-map coverage is incomplete")

    raw_check = json.loads((raw / "rustbox-cargo-check.json").read_text())
    stable_check = json.loads((stable / "rustbox-cargo-check.json").read_text())
    raw_type_errors = sum(error.get("code") == "E0308" for error in raw_check["errors"])
    if raw_check["build_finished_success"] or raw_type_errors != 8:
        raise RuntimeError("Less raw translator diagnostic baseline changed")
    if not stable_check["build_finished_success"] or stable_check["errors"]:
        raise RuntimeError("Less stable translation does not compile")

    raw_inventory = inventory(raw)
    stable_inventory = inventory(stable)
    if any(raw_inventory["holes"].values()) or any(stable_inventory["holes"].values()):
        raise RuntimeError("Less translation contains a generated hole")
    repairs_path = stable / "rustbox-less-repairs.json"
    repairs = json.loads(repairs_path.read_text())
    if repairs["repair_count"] != 8 or repairs["semantic_algorithm_changes"] != 0:
        raise RuntimeError("Less repair ledger changed")
    modernization_path = stable / "rustbox-modernization.json"
    archive = stable / "target/release/libless_710_normalized_audit.a"
    exports = {name: symbol_count(archive, name) for name in ENTRYPOINTS}
    if any(count != 1 for count in exports.values()):
        raise RuntimeError("Less translated entrypoints are not unique")

    payload = {
        "schema": 1,
        "recorded_at": "2026-11-22",
        "release": "710",
        "status": "complete stable translation compiles without holes; hybrid parity verified separately",
        "input": {
            "compile_commands": len(commands),
            "compile_database_sha256": sha256(database),
            "production_sources": sources,
            "declaration_maps": len(declaration_maps),
        },
        "translator": {
            "name": "C2Rust",
            "version": "0.22.1",
            "fail_on_error": True,
            "preserve_unused_functions": True,
            "omitted_sources": [],
            "generated_holes": 0,
            "raw_compile_type_errors": raw_type_errors,
            "stable_repairs": repairs,
        },
        "raw_translation": {**raw_inventory, "cargo_check": raw_check},
        "stable_translation": {
            **stable_inventory,
            "cargo_check": stable_check,
            "modernization_manifest_sha256": sha256(modernization_path),
            "repair_manifest_sha256": sha256(repairs_path),
            "archive": {
                "bytes": archive.stat().st_size,
                "sha256": sha256(archive),
                "entrypoint_definition_counts": exports,
            },
        },
        "dependencies": {"rust_crates": ["libc"]},
        "configuration": {"selinux": False, "systemd": False},
        "hardening": {
            "raw_pointers_and_unsafe_are_inventory_only": True,
            "later_order": [
                "eliminate raw pointers and unsafe",
                "replace std and libc crate use with Rustbox-owned no_std runtime",
            ],
        },
        "next_gate": "integrate less and lessecho into the unified multicall executable",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "commands": len(commands),
        "holes": 0,
        "repairs": repairs["repair_count"],
        "raw_pointers": stable_inventory["raw_pointer_type_occurrences"],
        "rust_lines": stable_inventory["rust_lines"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
