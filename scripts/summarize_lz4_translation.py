#!/usr/bin/env python3
"""Publish reproducible evidence for LZ4's complete C2Rust translation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


ENTRYPOINT = "rustbox_lz4_main"
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
    analysis = repository / "work/analysis/lz4-1.11.1"
    base = analysis / "translations/c2rust-0.22.1"
    raw = base / "lz4-1.11.1-normalized-audit"
    stable = base / "lz4-1.11.1-stable"
    database = analysis / "normalized/c2rust-compdb/compile_commands.json"
    normalization = repository / "evidence/lz4-1.11.1-normalization.json"

    commands = json.loads(database.read_text())
    prefix = "/rustbox-lz4/normalized-clang/"
    sources = [str(record["file"]) for record in commands]
    if any(not source.startswith(prefix) for source in sources):
        raise RuntimeError("LZ4 C2Rust database escapes normalized source")
    production_sources = sorted({source.removeprefix(prefix) for source in sources})
    expected_sources = json.loads(
        (repository / "evidence/lz4-1.11.1-oracle.json").read_text()
    )["inventory"]["production_sources"]
    if len(commands) != 12 or production_sources != expected_sources:
        raise RuntimeError("LZ4 C2Rust database is incomplete")
    if list(raw.rglob("*.c_decls.json")):
        raise RuntimeError("LZ4 unexpectedly emitted partial declaration maps")

    raw_check = json.loads((raw / "rustbox-cargo-check.json").read_text())
    stable_check = json.loads((stable / "rustbox-cargo-check.json").read_text())
    for label, check in (("raw", raw_check), ("stable", stable_check)):
        if not check["build_finished_success"] or check["errors"]:
            raise RuntimeError(f"{label} LZ4 Rust crate does not compile")
    if "nightly" not in raw_check["rustc"] or "rustc 1.99.0" not in stable_check["rustc"]:
        raise RuntimeError("LZ4 Rust toolchain evidence changed")

    raw_inventory = rust_inventory(raw)
    stable_inventory = rust_inventory(stable)
    if any(raw_inventory[name] for name in HOLES):
        raise RuntimeError("raw generated LZ4 Rust contains a translation hole")
    if any(stable_inventory[name] for name in HOLES):
        raise RuntimeError("stable LZ4 Rust contains a translation hole")
    if raw_inventory["rust_files"] != 14 or stable_inventory["rust_files"] != 14:
        raise RuntimeError("LZ4 Rust file inventory changed")

    raw_cargo = raw.joinpath("Cargo.toml").read_text()
    stable_cargo = stable.joinpath("Cargo.toml").read_text()
    if "f128" in raw_cargo or "f128" in stable_cargo:
        raise RuntimeError("LZ4 translation retained the incompatible f128 dependency")
    if '[dependencies]\nlibc = "0.2"' not in raw_cargo:
        raise RuntimeError("LZ4 generated dependency set changed")

    archive = stable / "target/release/liblz4_1_11_1_normalized_audit.a"
    if exported_count(archive, ENTRYPOINT) != 1:
        raise RuntimeError("LZ4 stable archive entrypoint is not unique")
    modernization_path = stable / "rustbox-modernization.json"
    modernization = json.loads(modernization_path.read_text())
    if len(modernization["changes"]) != 7:
        raise RuntimeError("LZ4 stable modernization changed")
    atomic_rewrites = sum(
        item.get("atomic_xchg_acquire_i32_rewrites", 0)
        for item in modernization["changes"]
    )
    if atomic_rewrites != 1:
        raise RuntimeError("LZ4 stable atomic mapping changed")

    normalization_record = json.loads(normalization.read_text())
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-21",
        "release": "1.11.1",
        "status": "complete stable translation compiles without holes; hybrid parity verified separately",
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
            "generated_rust_semantic_repairs": 0,
            "normalized_c_sources": 3,
            "raw_compile_metadata": {
                "source_unchanged": True,
                "compiler_crate_attribute": "feature(c_variadic)",
                "reason": "C2Rust emitted VaList declarations but omitted their historical-nightly crate feature",
            },
            "stable_atomic_mapping": {
                "count": atomic_rewrites,
                "from": "core::intrinsics::atomic_xchg_acquire on C sig_atomic_t",
                "to": "AtomicI32::swap with Ordering::Acquire",
            },
            "declaration_map_emission": {
                "enabled": False, "partial_maps_accepted": False,
            },
        },
        "raw_translation": {**raw_inventory, "cargo_check": raw_check},
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
        "dependencies": {
            "rust_crates": ["libc"],
            "f128_removed_by_verified_c_normalization": True,
        },
        "configuration": {"external_liblz4": False, "selinux": False, "systemd": False},
        "hardening": {
            "raw_pointers_and_unsafe_are_inventory_only": True,
            "later_order": [
                "eliminate raw pointers and unsafe",
                "replace std and libc crate use with Rustbox-owned no_std runtime",
            ],
        },
        "next_gate": "link rustbox_lz4_main and retain canonical parity in the unified multicall executable",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "commands": len(commands),
        "entrypoints": 1,
        "holes": sum(raw_inventory[name] for name in HOLES),
        "raw_pointers": stable_inventory["raw_pointer_type_occurrences"],
        "rust_files": stable_inventory["rust_files"],
        "rust_lines": stable_inventory["rust_lines"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
