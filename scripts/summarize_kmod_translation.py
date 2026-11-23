#!/usr/bin/env python3
"""Publish reproducible Kmod C2Rust translation evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


HOLES = ("compile_error!", "todo!", "unimplemented!", "C2Rust Translation Error")
ENTRYPOINT = "rustbox_kmod_main"


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


def symbol_count(archive: Path, symbol: str) -> int:
    output = subprocess.check_output(
        ["nm", "-g", "--defined-only", str(archive)], text=True, errors="replace"
    )
    return sum(line.split()[-1:] == [symbol] for line in output.splitlines())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.repository.resolve()
    archive = args.archive.resolve()
    analysis = root / "work/analysis/kmod-34.3"
    base = analysis / "translations/c2rust-0.22.1"
    audit = base / "kmod-34.3-normalized-audit"
    stable = base / "kmod-34.3-stable"
    database = analysis / "normalized/c2rust-compdb/compile_commands.json"

    oracle_path = root / "evidence/kmod-34.3-oracle.json"
    oracle = json.loads(oracle_path.read_text())
    normalization_path = root / "evidence/kmod-34.3-normalization.json"
    commands = json.loads(database.read_text())
    translated = {
        str(record["file"]).split("/normalized-source/", 1)[1] for record in commands
    }
    expected = set(oracle["production_closure"]["relative_paths"])
    if len(commands) != 26 or len(translated) != 26 or translated != expected:
        raise RuntimeError("Kmod translation closure changed")
    if any("-DRUSTBOX_MULTICALL=1" not in record["arguments"] for record in commands):
        raise RuntimeError("Kmod multicall translation define is missing")

    audit_inventory = inventory(audit)
    stable_inventory = inventory(stable)
    if audit_inventory["rust_files"] != 28 or stable_inventory["rust_files"] != 28:
        raise RuntimeError("Kmod translated Rust inventory changed")
    if any(audit_inventory["holes"].values()) or any(stable_inventory["holes"].values()):
        raise RuntimeError("Kmod translation contains a hole")

    raw_cargo = json.loads((audit / "rustbox-cargo-check.json").read_text())
    stable_cargo = json.loads((stable / "rustbox-cargo-check.json").read_text())
    if not raw_cargo["build_finished_success"] or raw_cargo["errors"]:
        raise RuntimeError("Kmod untouched translation does not compile on pinned nightly")
    if not stable_cargo["build_finished_success"] or stable_cargo["errors"]:
        raise RuntimeError("Kmod stable translation does not compile")
    if raw_cargo["toolchain_request"] != "nightly-2023-04-15":
        raise RuntimeError("Kmod raw C2Rust toolchain changed")

    finalization_path = stable / "rustbox-kmod-stable.json"
    finalization = json.loads(finalization_path.read_text())
    if finalization["stable_representation_repairs"] != 12:
        raise RuntimeError("Kmod stable representation repair count changed")
    if not archive.is_file():
        raise RuntimeError("Kmod stable archive is missing")
    entrypoints = symbol_count(archive, ENTRYPOINT)
    if entrypoints != 1:
        raise RuntimeError("Kmod translated entrypoint is not unique")

    evidence = {
        "schema": 1,
        "release": "34.3",
        "recorded_at": "2026-11-24",
        "status": "complete no-hole translation and stable hybrid-ready Rust archive",
        "input": {
            "compile_commands": len(commands),
            "compile_database_sha256": sha256(database),
            "oracle_evidence_sha256": sha256(oracle_path),
            "normalization_evidence_sha256": sha256(normalization_path),
        },
        "translator": {
            "name": "C2Rust",
            "version": "0.22.1",
            "fail_on_error": True,
            "preserve_unused_functions": True,
            "translated_c_sources": 26,
            "translation_holes": 0,
        },
        "complete_translation": {**audit_inventory, "cargo_check": raw_cargo},
        "stable_translation": {
            **stable_inventory,
            "active_translated_c_sources": 26,
            "canonical_c_sources": [],
            "stable_representation_repairs": 12,
            "cargo_check": stable_cargo,
            "archive": {
                "bytes": archive.stat().st_size,
                "sha256": sha256(archive),
                "entrypoint_definition_counts": {ENTRYPOINT: entrypoints},
            },
            "modernization_manifest_sha256": sha256(
                stable / "rustbox-modernization.json"
            ),
            "finalization_manifest_sha256": sha256(finalization_path),
        },
        "hardening": {
            "raw_pointers_and_unsafe_are_inventory_only": True,
            "deferred_until_all_applets_complete": True,
        },
        "next_gate": "prove hybrid parity and link all seven Kmod names into Rustbox",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "canonical_c_sources": 0,
        "holes": 0,
        "raw_pointers": stable_inventory["raw_pointer_type_occurrences"],
        "translated_sources": 26,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
