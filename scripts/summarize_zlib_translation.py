#!/usr/bin/env python3
"""Publish reproducible evidence for the full zlib C2Rust audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


HOLES = {
    "compile_error_macros": re.compile(r"\bcompile_error!"),
    "todo_macros": re.compile(r"\btodo!"),
    "unimplemented_macros": re.compile(r"\bunimplemented!"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/zlib-1.4"
    crate = analysis / "translations/c2rust-0.22.1/zlib-1.4-normalized-audit"
    database = analysis / "normalized/c2rust-compile-commands.json"
    normalization = repository / "evidence/zlib-1.4-normalization.json"
    cargo_check_path = crate / "rustbox-cargo-check.json"
    cargo_check = json.loads(cargo_check_path.read_text())
    if not cargo_check["build_finished_success"] or cargo_check["errors"]:
        raise RuntimeError("generated audit crate does not compile unchanged")

    commands = json.loads(database.read_text())
    names = sorted(Path(record["file"]).name for record in commands)
    if len(commands) != 15 or len(set(names)) != 15:
        raise RuntimeError("zlib C2Rust database is incomplete")
    declaration_maps = sorted(crate.glob("src/*.c_decls.json"))
    rust_files = sorted(crate.rglob("*.rs"))
    if len(declaration_maps) != 15:
        raise RuntimeError("zlib declaration maps are incomplete")
    combined = "\n".join(path.read_text(encoding="utf-8") for path in rust_files)
    holes = {name: len(pattern.findall(combined)) for name, pattern in HOLES.items()}
    if any(holes.values()):
        raise RuntimeError(f"generated zlib Rust contains translation holes: {holes!r}")

    evidence = {
        "schema": 1,
        "status": "full audit translation compiles unchanged; stable integration pending",
        "release": "1.4",
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
            "direct_common_flags": True,
            "reason_for_direct_flags": (
                "C2Rust 0.22.1 routes the Bear JSON filename through ClangTool's "
                "directory-only -p interface; the selector proves every production "
                "command has one identical flag vector before passing it directly."
            ),
        },
        "audit": {
            "rust_files": len(rust_files),
            "rust_bytes": sum(path.stat().st_size for path in rust_files),
            "file_sha256": {
                str(path.relative_to(crate)): sha256(path) for path in rust_files
            },
            "declaration_maps": len(declaration_maps),
            "declaration_map_sha256": {
                str(path.relative_to(crate)): sha256(path) for path in declaration_maps
            },
            **holes,
            "generated_rust_repairs": 0,
            "raw_pointer_type_occurrences": len(re.findall(r"\*(?:mut|const)\s+", combined)),
            "unsafe_function_occurrences": len(re.findall(r"\bunsafe\s+(?:extern\s+\"C\"\s+)?fn\b", combined)),
            "unsafe_block_occurrences": len(re.findall(r"\bunsafe\s*\{", combined)),
            "cargo_check": cargo_check,
        },
        "next_gate": "stable-toolchain modernization and canonical C/Rust differential library tests",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "commands": len(commands),
        "holes": sum(holes.values()),
        "raw_pointers": evidence["audit"]["raw_pointer_type_occurrences"],
        "rust_files": len(rust_files),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
