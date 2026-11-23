#!/usr/bin/env python3
"""Publish reproducible GNU Bison C2Rust translation evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


HOLES = ("compile_error!", "todo!", "unimplemented!", "C2Rust Translation Error")
ENTRYPOINT = "rustbox_bison_main"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(crate: Path) -> dict[str, object]:
    sources = sorted(crate.rglob("*.rs"))
    text = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    return {
        "rust_files": len(sources),
        "rust_bytes": sum(path.stat().st_size for path in sources),
        "raw_pointer_type_occurrences": len(re.findall(r"\*(?:mut|const)\s+", text)),
        "unsafe_function_occurrences": len(
            re.findall(r'\bunsafe\s+(?:extern\s+"C"\s+)?fn\b', text)
        ),
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
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.repository.resolve()
    analysis = root / "work/analysis/bison-3.8.2"
    base = analysis / "translations/c2rust-0.22.1"
    audit = base / "bison-3.8.2-normalized-audit"
    linked = base / "bison-3.8.2-linked"
    stable = base / "bison-3.8.2-stable"

    database = analysis / "normalized/c2rust-compdb/compile_commands.json"
    commands = json.loads(database.read_text())
    if len(commands) != 152 or len({record["file"] for record in commands}) != 152:
        raise RuntimeError("Bison translation closure changed")
    if any(record["file"].endswith(("/lib/main.c", "/lib/yyerror.c")) for record in commands):
        raise RuntimeError("standalone liby sources entered the Bison applet closure")

    audit_inventory = inventory(audit)
    stable_inventory = inventory(stable)
    if audit_inventory["rust_files"] != 154 or stable_inventory["rust_files"] != 154:
        raise RuntimeError("Bison translated Rust inventory changed")
    if any(audit_inventory["holes"].values()) or any(stable_inventory["holes"].values()):
        raise RuntimeError("Bison translation contains a hole")

    cross = json.loads((linked / "rustbox-cross-module-types.json").read_text())
    expected_types = [
        "derivation", "gl_map_impl", "gl_oset_impl", "hash_table",
        "lbitset_elt_struct", "parse_state", "quoting_options", "tbitset_elt_struct",
    ]
    if cross["changed_files"] != 41 or cross["linked_types"] != expected_types:
        raise RuntimeError("Bison cross-module type closure changed")

    finalization = json.loads((stable / "rustbox-bison-stable.json").read_text())
    boundary = finalization["changes"][2]
    expected_c = [
        "lib/printf-args.c", "lib/printf-frexpl.c",
        "lib/printf-parse.c", "lib/vasnprintf.c",
    ]
    if boundary["canonical_c_residue"] != expected_c:
        raise RuntimeError("Bison canonical C ABI boundary changed")
    active_modules = len(re.findall(r"^pub mod ", (stable / "lib.rs").read_text(), re.MULTILINE))
    if active_modules != 155:
        raise RuntimeError(f"Bison active Rust module count changed: {active_modules}")

    cargo = json.loads((stable / "rustbox-cargo-check.json").read_text())
    if not cargo["build_finished_success"] or cargo["errors"]:
        raise RuntimeError("Bison stable Rust crate does not compile")
    archive = stable / "target/release/libbison_3_8_2_normalized_audit.a"
    if symbol_count(archive, ENTRYPOINT) != 1:
        raise RuntimeError("Bison translated entrypoint is not unique")

    evidence = {
        "schema": 1,
        "release": "3.8.2",
        "recorded_at": "2026-11-23",
        "status": "complete no-hole translation and stable hybrid-ready Rust archive",
        "input": {
            "compile_commands": len(commands),
            "compile_database_sha256": sha256(database),
            "normalization_evidence_sha256": sha256(
                root / "evidence/bison-3.8.2-normalization.json"
            ),
        },
        "translator": {
            "name": "C2Rust",
            "version": "0.22.1",
            "fail_on_error": True,
            "preserve_unused_functions": True,
            "translated_c_sources": 152,
            "translation_holes": 0,
            "cross_module_type_links": cross["linked_types"],
            "cross_module_changed_files": cross["changed_files"],
        },
        "complete_translation": audit_inventory,
        "stable_translation": {
            **stable_inventory,
            "active_translated_c_sources": 148,
            "rust_module_declarations": active_modules,
            "canonical_c_bridge_sources": expected_c,
            "cargo_check": cargo,
            "archive": {
                "bytes": archive.stat().st_size,
                "sha256": sha256(archive),
                "entrypoint_definition_counts": {ENTRYPOINT: 1},
            },
            "cross_module_manifest_sha256": sha256(
                linked / "rustbox-cross-module-types.json"
            ),
            "modernization_manifest_sha256": sha256(
                stable / "rustbox-modernization.json"
            ),
            "finalization_manifest_sha256": sha256(
                stable / "rustbox-bison-stable.json"
            ),
        },
        "abi_boundary": {
            "reason": boundary["semantic_basis"],
            "target": finalization["target"],
            "prime_table_representation_casts": 254,
        },
        "hardening": {
            "raw_pointers_and_unsafe_are_inventory_only": True,
            "deferred_until_all_applets_complete": True,
        },
        "next_gate": (
            "link the four canonical C objects, embed C/C++ skeleton resources, "
            "route GNU M4 internally, and run the canonical differential"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "active_translated_c_sources": 148,
        "canonical_c_sources": len(expected_c),
        "holes": 0,
        "translated_sources": len(commands),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
