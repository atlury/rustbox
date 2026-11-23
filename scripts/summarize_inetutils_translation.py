#!/usr/bin/env python3
"""Publish reproducible GNU Inetutils C2Rust translation-audit evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


HOLES = ("compile_error!", "todo!", "unimplemented!", "C2Rust Translation Error")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(crate: Path) -> dict[str, object]:
    sources = sorted(crate.rglob("*.rs"))
    texts = [path.read_text(encoding="utf-8") for path in sources]
    text = "\n".join(texts)
    return {
        "rust_files": len(sources),
        "rust_lines": sum(value.count("\n") for value in texts),
        "rust_bytes": sum(path.stat().st_size for path in sources),
        "raw_pointer_type_occurrences": len(re.findall(r"\*(?:mut|const)\s+", text)),
        "unsafe_function_occurrences": len(
            re.findall(r'\bunsafe\s+(?:extern\s+"C"\s+)?fn\b', text)
        ),
        "unsafe_block_occurrences": len(re.findall(r"\bunsafe\s*\{", text)),
        "holes": {term: text.count(term) for term in HOLES},
    }


def symbol_counts(archive: Path, symbols: list[str]) -> dict[str, int]:
    output = subprocess.check_output(
        ["nm", "-g", "--defined-only", str(archive)],
        text=True,
        errors="replace",
    )
    names = [line.split()[-1] for line in output.splitlines() if line.split()]
    return {symbol: names.count(symbol) for symbol in symbols}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.repository.resolve()
    analysis = root / "work/analysis/inetutils-2.8"
    base = analysis / "translations/c2rust-0.22.1"
    audit = base / "inetutils-2.8-normalized-audit"
    stable = base / "inetutils-2.8-stable"
    database = analysis / "normalized/c2rust-compdb/compile_commands.json"
    archive = base / "cargo-target/release/libinetutils_2_8_normalized_audit.a"

    normalization_path = root / "evidence/inetutils-2.8-normalization.json"
    normalization = json.loads(normalization_path.read_text())
    commands = json.loads(database.read_text())
    expected = set(normalization["build"]["production_sources"])
    translated = {
        str(record["file"]).split("/normalized-source/", 1)[1]
        for record in commands
    }
    if len(commands) != 288 or len(translated) != 288 or translated != expected:
        raise RuntimeError("Inetutils translation input closure changed")
    if any("-DRUSTBOX_MULTICALL=1" not in record["arguments"] for record in commands):
        raise RuntimeError("Inetutils multicall translation define is missing")

    audit_inventory = inventory(audit)
    stable_inventory = inventory(stable)
    if audit_inventory["rust_files"] != 290 or stable_inventory["rust_files"] != 290:
        raise RuntimeError("Inetutils translated Rust inventory changed")
    if any(audit_inventory["holes"].values()) or any(stable_inventory["holes"].values()):
        raise RuntimeError("Inetutils translation contains a hole")

    cargo = json.loads((stable / "rustbox-cargo-check.json").read_text())
    if not cargo["build_finished_success"] or cargo["errors"]:
        raise RuntimeError("Inetutils stable compile audit does not pass cargo check")
    if cargo["warning_codes"].get("clashing_extern_declarations") != 132:
        raise RuntimeError("Inetutils cross-program declaration inventory changed")
    if not archive.is_file():
        raise RuntimeError("Inetutils stable compile-audit archive is missing")

    entrypoints = normalization["normalization"]["entrypoints"]
    counts = symbol_counts(archive, sorted(entrypoints.values()))
    if any(value != 1 for value in counts.values()):
        raise RuntimeError(f"Inetutils translated entrypoint delta: {counts}")

    modernization_path = stable / "rustbox-modernization.json"
    modernization = json.loads(modernization_path.read_text())
    finalization_path = stable / "rustbox-inetutils-stable.json"
    finalization = json.loads(finalization_path.read_text())
    boundary = next(
        change for change in finalization["changes"]
        if "canonical_c_residue" in change
    )
    if (
        boundary["canonical_c_residue"] != "lib/printf-args.c"
        or boundary["omitted_rust_module"] != "src/lib/printf_args.rs"
    ):
        raise RuntimeError("Inetutils canonical C boundary changed")

    evidence = {
        "schema": 1,
        "release": "2.8",
        "recorded_at": "2026-11-24",
        "status": "complete no-hole translation and stable compile-audit archive",
        "input": {
            "compile_commands": len(commands),
            "compile_database_sha256": sha256(database),
            "normalization_evidence_sha256": sha256(normalization_path),
        },
        "translator": {
            "name": "C2Rust",
            "version": "0.22.1",
            "fail_on_error": True,
            "preserve_unused_functions": True,
            "translated_c_sources": 288,
            "translation_holes": 0,
        },
        "complete_translation": audit_inventory,
        "stable_compile_audit": {
            **stable_inventory,
            "active_translated_c_sources": 287,
            "canonical_c_bridge_sources": ["lib/printf-args.c"],
            "cargo_check": cargo,
            "archive": {
                "bytes": archive.stat().st_size,
                "sha256": sha256(archive),
                "entrypoint_definition_counts": counts,
            },
            "duplicate_exports_mangled": len(
                modernization.get("duplicate_exports_mangled", [])
            ),
            "modernization_manifest_sha256": sha256(modernization_path),
            "finalization_manifest_sha256": sha256(finalization_path),
        },
        "abi_boundary": {
            "reason": boundary["semantic_basis"],
            "target": finalization["target"],
        },
        "partition_requirement": {
            "combined_archive_is_not_hybrid_ready": True,
            "clashing_extern_declarations": 132,
            "reason": (
                "GNU Inetutils is 26 separate canonical programs whose private C "
                "names overlap; each program must retain its own symbol namespace"
            ),
        },
        "hardening": {
            "raw_pointers_and_unsafe_are_inventory_only": True,
            "deferred_until_all_applets_complete": True,
        },
        "next_gate": (
            "build program-scoped Rust/C hybrids, prove all 26 against their "
            "canonical executables, then namespace and link them into Rustbox"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "active_translated_c_sources": 287,
        "canonical_c_sources": 1,
        "entrypoints": len(counts),
        "holes": 0,
        "raw_pointers": stable_inventory["raw_pointer_type_occurrences"],
        "translated_sources": len(commands),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
