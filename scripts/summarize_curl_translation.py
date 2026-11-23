#!/usr/bin/env python3
"""Publish reproducible curl C2Rust translation evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


HOLES = ("compile_error!", "todo!", "unimplemented!", "C2Rust Translation Error")
ENTRYPOINT = "rustbox_curl_main"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(crate: Path) -> dict[str, object]:
    sources = sorted(crate.rglob("*.rs"))
    text = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    return {
        "rust_files": len(sources),
        "rust_lines": sum(
            path.read_text(encoding="utf-8").count("\n") for path in sources
        ),
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
        ["nm", "-g", "--defined-only", str(archive)],
        text=True,
        errors="replace",
    )
    return sum(line.split()[-1:] == [symbol] for line in output.splitlines())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.repository.resolve()
    analysis = root / "work/analysis/curl-8.23.0"
    base = analysis / "translations/c2rust-0.22.1"
    audit = base / "curl-8.23.0-normalized-audit"
    stable = base / "curl-8.23.0-stable"
    database = analysis / "normalized/c2rust-compdb/compile_commands.json"

    commands = json.loads(database.read_text())
    files = [str(record["file"]) for record in commands]
    if len(commands) != 240 or len(set(files)) != 240:
        raise RuntimeError("curl translation closure changed")
    if any("-DUNITTESTS" in record["arguments"] for record in commands):
        raise RuntimeError("curl UNITTESTS action entered the production translation")
    for define in ("-DRUSTBOX_MULTICALL=1", "-DCURL_DISABLE_TYPECHECK=1"):
        if any(define not in record["arguments"] for record in commands):
            raise RuntimeError(f"curl translation define missing: {define}")

    oracle = json.loads((root / "evidence/curl-8.23.0-oracle.json").read_text())
    expected = set(oracle["scope"]["production_sources"])
    translated = set()
    for path in files:
        relative = path.split("/c2rust-source/", 1)[1]
        if relative in ("src/tool_ca_embed.c", "src/tool_hugehelp.c"):
            relative = "generated/" + relative
        translated.add(relative)
    if translated != expected:
        raise RuntimeError(
            f"curl translated source delta: {sorted(translated ^ expected)}"
        )

    audit_inventory = inventory(audit)
    stable_inventory = inventory(stable)
    if audit_inventory["rust_files"] != 242 or stable_inventory["rust_files"] != 242:
        raise RuntimeError("curl translated Rust inventory changed")
    if any(audit_inventory["holes"].values()) or any(stable_inventory["holes"].values()):
        raise RuntimeError("curl translation contains a hole")

    raw_text = "\n".join(
        path.read_text(encoding="utf-8") for path in audit.rglob("*.rs")
    )
    if raw_text.count(f"fn {ENTRYPOINT}") != 1:
        raise RuntimeError("curl raw translated entrypoint is not unique")
    f128_files = sorted(
        path.relative_to(audit).as_posix()
        for path in audit.rglob("*.rs")
        if "::f128" in path.read_text(encoding="utf-8")
    )
    if f128_files != ["src/lib/mprintf.rs"]:
        raise RuntimeError(f"curl f128 boundary changed: {f128_files}")

    finalization_path = stable / "rustbox-curl-stable.json"
    finalization = json.loads(finalization_path.read_text())
    if len(finalization["changes"]) != 1:
        raise RuntimeError("curl stable boundary manifest changed")
    boundary = finalization["changes"][0]
    if (
        boundary["canonical_c_residue"] != "lib/mprintf.c"
        or boundary["omitted_rust_module"] != "src/lib/mprintf.rs"
        or boundary["removed_rust_dependencies"] != ["f128", "num-traits"]
    ):
        raise RuntimeError("curl canonical C boundary changed")
    stable_cargo = (stable / "Cargo.toml").read_text(encoding="utf-8")
    if "f128" in stable_cargo or "num-traits" in stable_cargo:
        raise RuntimeError("curl stable crate retained inactive dependencies")

    raw_modules = len(re.findall(
        r"^pub mod ", (audit / "lib.rs").read_text(encoding="utf-8"), re.MULTILINE
    ))
    stable_modules = len(re.findall(
        r"^pub mod ", (stable / "lib.rs").read_text(encoding="utf-8"), re.MULTILINE
    ))
    if raw_modules != 250 or stable_modules != 249:
        raise RuntimeError("curl active Rust module closure changed")

    cargo = json.loads((stable / "rustbox-cargo-check.json").read_text())
    if not cargo["build_finished_success"] or cargo["errors"]:
        raise RuntimeError("curl stable Rust crate does not compile")
    archive = stable / "target/release/libcurl_8_23_0_normalized_audit.a"
    entrypoints = symbol_count(archive, ENTRYPOINT)
    if entrypoints != 1:
        raise RuntimeError("curl translated archive entrypoint is not unique")

    evidence = {
        "schema": 1,
        "release": "8.23.0",
        "recorded_at": "2026-11-23",
        "status": "complete no-hole translation and stable hybrid-ready Rust archive",
        "input": {
            "compile_commands": len(commands),
            "excluded_unit_test_actions": 237,
            "compile_database_sha256": sha256(database),
            "normalization_evidence_sha256": sha256(
                root / "evidence/curl-8.23.0-normalization.json"
            ),
        },
        "translator": {
            "name": "C2Rust",
            "version": "0.22.1",
            "fail_on_error": True,
            "preserve_unused_functions": True,
            "translated_c_sources": 240,
            "translation_holes": 0,
            "translation_only_configuration": {
                "CURL_DISABLE_TYPECHECK": True,
                "HAVE_ATOMIC": False,
                "linux_swab_portable_fallback": True,
            },
        },
        "complete_translation": {
            **audit_inventory,
            "rust_module_declarations": raw_modules,
            "f128_source_modules": f128_files,
        },
        "stable_translation": {
            **stable_inventory,
            "active_translated_c_sources": 239,
            "rust_module_declarations": stable_modules,
            "canonical_c_bridge_sources": ["lib/mprintf.c"],
            "rust_dependencies": ["c2rust-bitfields", "libc"],
            "cargo_check": cargo,
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
        "abi_boundary": {
            "reason": boundary["semantic_basis"],
            "target": finalization["target"],
        },
        "hardening": {
            "raw_pointers_and_unsafe_are_inventory_only": True,
            "deferred_until_all_applets_complete": True,
        },
        "next_gate": (
            "link lib/mprintf.c with the stable Rust archive, prove curl and "
            "libcurl canonical differential parity, and integrate curl plus curl-config"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "active_translated_c_sources": 239,
        "canonical_c_sources": 1,
        "holes": 0,
        "raw_pointers": stable_inventory["raw_pointer_type_occurrences"],
        "translated_sources": len(commands),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
