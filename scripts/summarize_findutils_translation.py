#!/usr/bin/env python3
"""Summarize complete and reachable GNU Findutils C2Rust evidence."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "work/analysis/findutils-4.10.0"
BASE = ANALYSIS / "translations/c2rust-0.22.1"
AUDIT = BASE / "findutils-4.10.0-normalized-audit"
COMPLETE = BASE / "findutils-4.10.0-complete-stable"
REACHABLE = BASE / "findutils-4.10.0-stable"
HOLES = ("compile_error!", "unimplemented!", "todo!", "C2Rust Translation Error")
ENTRYPOINTS = (
    "rustbox_find_main", "rustbox_xargs_main", "rustbox_locate_main", "rustbox_frcode_main",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rust_inventory(root: Path) -> dict[str, object]:
    sources = sorted(root.rglob("*.rs"))
    text = "\n".join(path.read_text(errors="replace") for path in sources)
    return {
        "rust_files": len(sources),
        "rust_bytes": sum(path.stat().st_size for path in sources),
        "holes": {term: text.count(term) for term in HOLES},
    }


def symbol_count(archive: Path, symbol: str) -> int:
    output = subprocess.check_output(["nm", "-g", str(archive)], text=True, errors="replace")
    return sum(line.split()[-1:] == [symbol] for line in output.splitlines())


def main() -> int:
    database = ANALYSIS / "normalized/c2rust-compdb/compile_commands.json"
    records = json.loads(database.read_text())
    batch_manifest = json.loads(
        (ANALYSIS / "normalized/c2rust-compdb-batches/manifest.json").read_text()
    )
    if len(records) != 193 or batch_manifest["commands"] != 193 or len(batch_manifest["batches"]) != 8:
        raise RuntimeError("Findutils C2Rust production or batch closure changed")
    if batch_manifest["declaration_map_exceptions"] != ["/gl/lib/parse-datetime.c"]:
        raise RuntimeError("Findutils declaration-map exception changed")

    audit_modules = sorted(AUDIT.glob("batch-*/src/**/*.rs"))
    audit_maps = sorted(AUDIT.glob("batch-*/src/**/*.c_decls.json"))
    if len(audit_modules) != 193 or len(audit_maps) != 192:
        raise RuntimeError("Findutils strict translation inventory changed")
    audit_text = "\n".join(path.read_text(errors="replace") for path in audit_modules)
    if any(term in audit_text for term in HOLES):
        raise RuntimeError("Findutils strict translation contains a hole")

    complete_combination = json.loads(
        (BASE / "findutils-4.10.0-complete/rustbox-combination.json").read_text()
    )
    reachable_combination = json.loads(
        (BASE / "findutils-4.10.0-reachable/rustbox-combination.json").read_text()
    )
    excluded = ["printf_args", "printf_parse", "vasnprintf"]
    if complete_combination["modules"] != 193 or complete_combination["excluded_modules"]:
        raise RuntimeError("complete Findutils combination changed")
    if (
        reachable_combination["modules"] != 190
        or reachable_combination["excluded_modules"] != excluded
    ):
        raise RuntimeError("reachable Findutils combination changed")

    complete_log = (ANALYSIS / "normalized/c2rust-complete-check.log").read_text(errors="replace")
    complete_errors = re.findall(r"^error\[(E\d+)\]: (.+)$", complete_log, re.MULTILINE)
    if len(complete_errors) != 1 or complete_errors[0][0] != "E0277" or "VaArgSafe" not in complete_errors[0][1]:
        raise RuntimeError(f"complete Findutils diagnostic changed: {complete_errors}")
    stable_log = (ANALYSIS / "normalized/c2rust-stable-check.log").read_text(errors="replace")
    if "Finished `release` profile" not in stable_log or re.search(r"^error(?:\[|:)", stable_log, re.MULTILINE):
        raise RuntimeError("reachable Findutils stable crate does not compile")

    complete_inventory = rust_inventory(COMPLETE)
    stable_inventory = rust_inventory(REACHABLE)
    if any(complete_inventory["holes"].values()) or any(stable_inventory["holes"].values()):
        raise RuntimeError("modernized Findutils crate contains a translation hole")
    archive = REACHABLE / "target/release/libfindutils_4_10_0_combined.a"
    counts = {name: symbol_count(archive, name) for name in ENTRYPOINTS}
    if set(counts.values()) != {1}:
        raise RuntimeError(f"Findutils entrypoint definitions changed: {counts}")

    modernization = json.loads((REACHABLE / "rustbox-modernization.json").read_text())
    evidence = {
        "schema": 1,
        "release": "4.10.0",
        "recorded_at": "2026-11-22",
        "status": "complete no-hole audit and stable reachable translation",
        "input": {
            "compile_commands": 193,
            "compile_database_sha256": sha256(database),
            "batches": 8,
            "batch_manifest_sha256": sha256(
                ANALYSIS / "normalized/c2rust-compdb-batches/manifest.json"
            ),
        },
        "translator": {
            "name": "C2Rust",
            "version": "0.22.1",
            "fail_on_error": True,
            "preserve_unused_functions": True,
            "translated_sources": 193,
            "translation_holes": 0,
            "declaration_maps": 192,
            "declaration_map_exception": "gl/lib/parse-datetime.c Bison #line spans",
            "complete_compile_diagnostic": {
                "code": complete_errors[0][0], "message": complete_errors[0][1],
                "reason": (
                    "Rust's sealed VaArgSafe ABI trait does not accept C2Rust's f128 wrapper "
                    "for x86_64 SysV C long double variadics"
                ),
            },
            "reachable_partition": {
                "rust_sources": 190,
                "canonical_c_bridge_sources": [
                    "gl/lib/printf-args.c", "gl/lib/printf-parse.c", "gl/lib/vasnprintf.c",
                ],
            },
        },
        "complete_translation": complete_inventory,
        "stable_translation": {
            **stable_inventory,
            "toolchain": "Rust 1.99.0",
            "cargo_check": "pass",
            "modernization_manifest_sha256": sha256(REACHABLE / "rustbox-modernization.json"),
            "modernized_files": len(modernization["changes"]),
            "archive": {
                "bytes": archive.stat().st_size,
                "sha256": sha256(archive),
                "entrypoint_definition_counts": counts,
            },
        },
        "next_gate": "integrate the verified hybrid personalities into the unified dispatcher",
    }
    output = ROOT / "evidence/findutils-4.10.0-c2rust.json"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"entrypoints": 4, "stable_modules": 190, "translated": 193}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
