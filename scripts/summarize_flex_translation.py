#!/usr/bin/env python3
"""Publish reproducible evidence for Flex's complete translated production closure."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "work/analysis/flex-2.6.4"
BASE = ANALYSIS / "translations/c2rust-0.22.1"
AUDIT = BASE / "flex-2.6.4-normalized-audit"
STABLE = BASE / "flex-2.6.4-stable"
ARCHIVE = STABLE / "target/release/libflex_2_6_4_normalized_audit.a"
HYBRID = ROOT / "build/flex-2.6.4-hybrid/flex"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(crate: Path) -> dict[str, object]:
    files = sorted(crate.rglob("*.rs"))
    combined = "\n".join(path.read_text(errors="replace") for path in files)
    holes = re.findall(r"\b(?:unimplemented|todo|compile_error)!\s*\(", combined)
    return {
        "rust_files": len(files),
        "rust_bytes": sum(path.stat().st_size for path in files),
        "translation_holes": len(holes),
        "raw_pointer_type_occurrences": len(re.findall(r"\*(?:mut|const)\s+", combined)),
        "unsafe_function_occurrences": len(
            re.findall(r'\bunsafe\s+(?:extern\s+"C"\s+)?fn\b', combined)
        ),
        "unsafe_block_occurrences": len(re.findall(r"\bunsafe\s*\{", combined)),
    }


def suite() -> dict[str, object]:
    path = ANALYSIS / "hybrid-suite-check.log"
    text = path.read_text(errors="replace")
    counts = {}
    for label in ("TOTAL", "PASS", "SKIP", "XFAIL", "FAIL", "XPASS", "ERROR"):
        match = re.search(rf"^# {label}:\s+(\d+)$", text, re.MULTILINE)
        if not match:
            raise RuntimeError(f"translated Flex suite lacks {label}")
        counts[label.lower()] = int(match.group(1))
    expected = {
        "total": 114, "pass": 114, "skip": 0, "xfail": 0,
        "fail": 0, "xpass": 0, "error": 0,
    }
    if counts != expected:
        raise RuntimeError(f"translated Flex suite changed: {counts}")
    return {**counts, "log_sha256": sha256(path)}


def main() -> int:
    compdb_path = ANALYSIS / "normalized/c2rust-compdb/compile_commands.json"
    compdb = json.loads(compdb_path.read_text())
    sources = {record["file"] for record in compdb}
    if len(compdb) != 21 or len(sources) != 21:
        raise RuntimeError("Flex translated production closure changed")

    audit = inventory(AUDIT)
    stable = inventory(STABLE)
    if audit["translation_holes"] or stable["translation_holes"]:
        raise RuntimeError("Flex translation contains a generated Rust hole")

    modernization_path = STABLE / "rustbox-modernization.json"
    modernization = json.loads(modernization_path.read_text())
    changes = modernization["changes"]
    if len(changes) != 22:
        raise RuntimeError("Flex stable-modernization surface changed")
    rewrites = {
        name: sum(int(change[name]) for change in changes)
        for name in ("as_va_list_rewrites", "va_list_impl_rewrites", "va_arg_rewrites")
    }
    if rewrites != {
        "as_va_list_rewrites": 23,
        "va_list_impl_rewrites": 3,
        "va_arg_rewrites": 1,
    }:
        raise RuntimeError(f"Flex deterministic modernization changed: {rewrites}")

    for name in ("cargo-check.log", "cargo-build.log", "cargo-hybrid.log"):
        if "Finished `release` profile" not in (STABLE / name).read_text(errors="replace"):
            raise RuntimeError(f"Flex stable build evidence is incomplete: {name}")
    if not ARCHIVE.is_file() or not HYBRID.is_file():
        raise RuntimeError("Flex archive or hybrid binary is absent")

    symbols = subprocess.run(
        ["nm", "-g", "--defined-only", str(HYBRID)], check=True,
        text=True, stdout=subprocess.PIPE,
    ).stdout
    entrypoints = ("rustbox_flex_main", "rustbox_flexpp_main", "rustbox_lex_main")
    for entrypoint in entrypoints:
        if len(re.findall(rf"\b{entrypoint}$", symbols, re.MULTILINE)) != 1:
            raise RuntimeError(f"Flex entrypoint changed: {entrypoint}")

    differential = json.loads((ANALYSIS / "translated-differential.json").read_text())
    if differential["cases"] != 14 or differential["passed"] != 14:
        raise RuntimeError("Flex translated differential is incomplete")
    frontends = json.loads((ANALYSIS / "hybrid-frontends.json").read_text())
    if frontends["cases"] != 3 or frontends["passed"] != 3:
        raise RuntimeError("Flex frontend differential is incomplete")

    valgrind = {}
    for label in ("help", "version", "invalid"):
        path = ANALYSIS / f"hybrid-valgrind-{label}.log"
        text = path.read_text(errors="replace")
        required = (
            "ERROR SUMMARY: 0 errors", "definitely lost: 0 bytes",
            "indirectly lost: 0 bytes", "possibly lost: 0 bytes",
        )
        if not all(item in text for item in required):
            raise RuntimeError(f"Flex translated resource check changed: {label}")
        valgrind[label] = {"errors": 0, "lost_bytes": 0, "log_sha256": sha256(path)}

    stripped = HYBRID.with_name("flex.stripped")
    needed = re.findall(
        r"Shared library: \[([^]]+)\]",
        HYBRID.with_name("flex.dynamic").read_text(errors="replace"),
    )
    evidence = {
        "schema": 1,
        "release": "2.6.4",
        "recorded_at": "2026-11-23",
        "status": "complete stable reachable translation without holes; hybrid parity verified",
        "normalization_evidence_sha256": sha256(ROOT / "evidence/flex-2.6.4-normalization.json"),
        "translation": {
            "tool": "c2rust 0.22.1",
            "strict": True,
            "preserve_unused_functions": True,
            "compile_commands": len(compdb),
            "production_sources": len(sources),
            "normalized_sources": 20,
            "generated_sources": 1,
            "compile_database_sha256": sha256(compdb_path),
            "raw_audit": audit,
            "stable": stable,
            "modernization": {
                "toolchain": modernization["stable_toolchain"],
                "changed_files": len(changes),
                "rewrites": rewrites,
                "ledger_sha256": sha256(modernization_path),
                "hand_edited_generated_rust": False,
            },
            "archive": {"bytes": ARCHIVE.stat().st_size, "sha256": sha256(ARCHIVE)},
        },
        "verification": {
            "upstream_suite": suite(),
            "canonical_differential": differential,
            "compatibility_frontends": frontends,
            "valgrind": valgrind,
        },
        "entrypoints": list(entrypoints),
        "hybrid": {
            "bytes": HYBRID.stat().st_size,
            "sha256": sha256(HYBRID),
            "stripped_bytes": stripped.stat().st_size,
            "stripped_sha256": sha256(stripped),
            "dynamic_dependencies": needed,
        },
        "deferred_post_applet_hardening": {
            "raw_pointers_and_unsafe_are_inventory_only": True,
            "static_zero_dt_needed": False,
            "size_optimization": False,
            "no_std": False,
        },
    }
    output = ROOT / "evidence/flex-2.6.4-c2rust.json"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "differential": differential["passed"],
        "frontends": frontends["passed"],
        "holes": stable["translation_holes"],
        "rust_files": stable["rust_files"],
        "upstream_tests": evidence["verification"]["upstream_suite"]["pass"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
