#!/usr/bin/env python3
"""Publish complete Procps-ng C2Rust and hybrid-parity evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


PROGRAMS = (
    "free", "hugetop", "kill", "pgrep", "pidof", "pidwait", "pkill",
    "pmap", "ps", "pwdx", "skill", "slabtop", "snice", "sysctl",
    "tload", "top", "uptime", "vmstat", "w", "watch",
)
ENTRYPOINTS = (
    "free", "hugetop", "kill", "pgrep", "pidof", "pmap", "ps", "pwdx",
    "skill", "slabtop", "sysctl", "tload", "top", "uptime", "vmstat", "w",
    "watch",
)
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
        "thread_local_attributes": text.count("#[thread_local]"),
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
    parser.add_argument("--hybrid", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.repository.resolve()
    archive = args.archive.resolve()
    hybrid = args.hybrid.resolve()
    analysis = root / "work/analysis/procps-ng-4.0.7"
    base = analysis / "translations/c2rust-0.22.1"
    audit = base / "procps-ng-4.0.7-normalized-audit"
    nightly = base / "procps-ng-4.0.7-nightly"
    database = analysis / "normalized/c2rust-compdb/compile_commands.json"

    oracle_path = root / "evidence/procps-ng-4.0.7-oracle.json"
    normalization_path = root / "evidence/procps-ng-4.0.7-normalization.json"
    oracle = json.loads(oracle_path.read_text())
    commands = json.loads(database.read_text())
    expected = set(oracle["production_closure"]["relative_paths"])
    translated = {
        str(record["file"]).split("/procps-ng-4.0.7/", 1)[1] for record in commands
    }
    if len(commands) != 49 or translated != expected:
        raise RuntimeError("Procps translation closure changed")
    if any("-DRUSTBOX_MULTICALL=1" not in record["arguments"] for record in commands):
        raise RuntimeError("Procps multicall translation define is missing")

    audit_inventory = inventory(audit)
    nightly_inventory = inventory(nightly)
    if audit_inventory["rust_files"] != 51 or nightly_inventory["rust_files"] != 51:
        raise RuntimeError("Procps translated Rust inventory changed")
    if any(audit_inventory["holes"].values()) or any(nightly_inventory["holes"].values()):
        raise RuntimeError("Procps translation contains a hole")
    if nightly_inventory["raw_pointer_type_occurrences"] != 32183:
        raise RuntimeError("Procps raw-pointer inventory changed")

    raw_cargo = json.loads((audit / "rustbox-cargo-check.json").read_text())
    raw_errors = [item for item in raw_cargo["errors"] if item["code"]]
    if raw_cargo["build_finished_success"] or [item["code"] for item in raw_errors] != [
        "E0425", "E0425", "E0054"
    ]:
        raise RuntimeError("Procps untouched C2Rust diagnostic baseline changed")
    nightly_cargo = json.loads((nightly / "rustbox-cargo-check.json").read_text())
    if not nightly_cargo["build_finished_success"] or nightly_cargo["errors"]:
        raise RuntimeError("repaired Procps translation does not compile")
    if nightly_cargo["toolchain_request"] != "nightly-2023-04-15":
        raise RuntimeError("Procps translated toolchain changed")

    finalization_path = nightly / "rustbox-procps-nightly.json"
    finalization = json.loads(finalization_path.read_text())
    if (
        finalization["semantic_repairs"] != 3
        or finalization["thread_local_attributes_preserved"] != 29
        or len(finalization["duplicate_exports_mangled"]) != 2
    ):
        raise RuntimeError("Procps translation repair inventory changed")
    if not archive.is_file():
        raise RuntimeError("Procps Rust archive is missing")
    entrypoint_counts = {
        f"rustbox_procps_{name}_main": symbol_count(
            archive, f"rustbox_procps_{name}_main"
        )
        for name in ENTRYPOINTS
    }
    if set(entrypoint_counts.values()) != {1}:
        raise RuntimeError("Procps translated entrypoint inventory changed")

    differential_path = hybrid / "differential.json"
    differential = json.loads(differential_path.read_text())
    if differential.get("cases") != 51 or differential.get("passed") != 51:
        raise RuntimeError("Procps hybrid differential changed")
    valgrind = {}
    for name in PROGRAMS:
        path = hybrid / f"valgrind-{name}.log"
        text = path.read_text(errors="replace")
        errors = re.search(r"ERROR SUMMARY: (\d+) errors", text)
        if name == "sysctl":
            if not errors or errors.group(1) != "1" or "definitely lost: 16 bytes in 1 blocks" not in text:
                raise RuntimeError("Procps hybrid sysctl allocation baseline changed")
            valgrind[name] = {"errors": 1, "definitely_lost_bytes": 16, "sha256": sha256(path)}
        else:
            if not errors or errors.group(1) != "0":
                raise RuntimeError(f"Procps hybrid {name} Valgrind baseline changed")
            valgrind[name] = {"errors": 0, "definitely_lost_bytes": 0, "sha256": sha256(path)}

    executable = hybrid / "procps"
    stripped = hybrid / "procps.stripped"
    dynamic_text = (hybrid / "procps.dynamic").read_text(errors="replace")
    dependencies = re.findall(r"Shared library: \[([^]]+)\]", dynamic_text)
    evidence = {
        "schema": 1,
        "release": "4.0.7",
        "recorded_at": "2026-11-24",
        "status": "complete no-hole translation and hybrid parity",
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
            "translated_c_sources": 49,
            "translation_holes": 0,
        },
        "untouched_translation": {**audit_inventory, "cargo_check": raw_cargo},
        "repaired_translation": {
            **nightly_inventory,
            "active_translated_c_sources": 49,
            "canonical_c_sources": [],
            "semantic_repairs": 3,
            "duplicate_exports_mangled": 2,
            "cargo_check": nightly_cargo,
            "archive": {
                "bytes": archive.stat().st_size,
                "sha256": sha256(archive),
                "entrypoint_definition_counts": entrypoint_counts,
            },
            "finalization_manifest_sha256": sha256(finalization_path),
        },
        "hybrid": {
            "public_programs": 20,
            "differential": {"cases": 51, "passed": 51, "sha256": sha256(differential_path)},
            "valgrind": valgrind,
            "executable": {"bytes": executable.stat().st_size, "sha256": sha256(executable)},
            "stripped": {"bytes": stripped.stat().st_size, "sha256": sha256(stripped)},
            "dynamic_dependencies": dependencies,
        },
        "hardening": {
            "raw_pointers_and_unsafe_are_inventory_only": True,
            "deferred_until_all_applets_complete": True,
            "static_external_library_elimination_deferred": True,
        },
        "next_gate": "link all 20 Procps names into the unified Rustbox multicall",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "hybrid_cases": 51,
        "holes": 0,
        "raw_pointers": nightly_inventory["raw_pointer_type_occurrences"],
        "translated_sources": 49,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
