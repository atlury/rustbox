#!/usr/bin/env python3
"""Publish complete Shadow C2Rust and hybrid-parity evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path


PROGRAMS = (
    "chage", "chfn", "chgpasswd", "chpasswd", "chsh", "faillog",
    "getsubids", "gpasswd", "groupadd", "groupdel", "groupmod", "grpck",
    "grpconv", "grpunconv", "lastlog", "login", "newgidmap", "newgrp",
    "newuidmap", "newusers", "nologin", "passwd", "pwck", "pwconv",
    "pwunconv", "su", "useradd", "userdel", "usermod", "vipw", "sg",
    "vigr",
)
ENGINES = tuple(name for name in PROGRAMS if name not in {"sg", "vigr"})
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


def symbol_counts(archive: Path) -> Counter[str]:
    output = subprocess.check_output(
        ["nm", "-g", "--defined-only", str(archive)], text=True, errors="replace"
    )
    return Counter(
        fields[-1]
        for line in output.splitlines()
        if (fields := line.split())
    )


def valgrind_summary(path: Path, name: str) -> dict[str, object]:
    text = path.read_text(errors="replace")
    errors = re.search(r"ERROR SUMMARY: (\d+) errors", text)
    if errors is None:
        raise RuntimeError(f"Shadow Valgrind summary is missing: {name}")
    result: dict[str, object] = {
        "errors": int(errors.group(1)),
        "sha256": sha256(path),
    }
    if name == "gpasswd":
        direct = re.search(r"definitely lost: ([0-9,]+) bytes", text)
        indirect = re.search(r"indirectly lost: ([0-9,]+) bytes", text)
        if (
            result["errors"] != 6 or direct is None or indirect is None
            or direct.group(1) != "48" or indirect.group(1) != "28"
        ):
            raise RuntimeError("Shadow gpasswd canonical allocation baseline changed")
        result.update({"definitely_lost_bytes": 48, "indirectly_lost_bytes": 28})
    elif result["errors"] != 0:
        raise RuntimeError(f"Shadow hybrid resource baseline changed: {name}")
    return result


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
    analysis = root / "work/analysis/shadow-4.20.4"
    base = analysis / "translations/c2rust-0.22.1"
    audit = base / "shadow-4.20.4-normalized-audit"
    nightly = base / "shadow-4.20.4-nightly"
    database = analysis / "c2rust-compdb/compile_commands.json"
    closure_path = analysis / "c2rust-compdb/closure.json"

    closure = json.loads(closure_path.read_text())
    commands = json.loads(database.read_text())
    if (
        closure["commands"] != 196
        or closure["canonical_production_sources"] != 201
        or len(closure["excluded_noninstalled_program_sources"]) != 5
        or len(commands) != 196
        or any("-DRUSTBOX_MULTICALL=1" not in record["arguments"] for record in commands)
    ):
        raise RuntimeError("Shadow strict translation closure changed")

    audit_inventory = inventory(audit)
    nightly_inventory = inventory(nightly)
    if audit_inventory["rust_files"] != 198 or nightly_inventory["rust_files"] != 198:
        raise RuntimeError("Shadow translated Rust inventory changed")
    if any(audit_inventory["holes"].values()) or any(nightly_inventory["holes"].values()):
        raise RuntimeError("Shadow translation contains a hole")
    if nightly_inventory["raw_pointer_type_occurrences"] != 31872:
        raise RuntimeError("Shadow raw-pointer inventory changed")

    raw_cargo = json.loads((audit / "rustbox-cargo-check.json").read_text())
    raw_codes = [item["code"] for item in raw_cargo["errors"] if item.get("code")]
    if raw_cargo["build_finished_success"] or raw_codes != ["E0308"] * 15:
        raise RuntimeError("Shadow untouched C2Rust diagnostic baseline changed")
    nightly_cargo = json.loads((nightly / "rustbox-cargo-check.json").read_text())
    if not nightly_cargo["build_finished_success"] or nightly_cargo["errors"]:
        raise RuntimeError("repaired Shadow translation does not type-check")
    if nightly_cargo["toolchain_request"] != "nightly-2023-04-15":
        raise RuntimeError("Shadow translated toolchain changed")

    repair_path = nightly / "rustbox-repairs.json"
    repairs = json.loads(repair_path.read_text())
    if (
        repairs["source_modules"] != 196
        or repairs["repair_sites"] != 22
        or len(repairs["repairs"]) != 21
        or len({item["path"] for item in repairs["repairs"]}) != 13
        or any(Path(item["path"]).is_absolute() for item in repairs["repairs"])
    ):
        raise RuntimeError("Shadow generated-Rust repair inventory changed")
    if not archive.is_file():
        raise RuntimeError("Shadow Rust archive is missing")
    definitions = symbol_counts(archive)
    entrypoints = {
        f"rustbox_shadow_{name}_main": definitions[f"rustbox_shadow_{name}_main"]
        for name in ENGINES
    }
    if set(entrypoints.values()) != {1}:
        raise RuntimeError("Shadow translated entrypoint inventory changed")

    differential_path = hybrid / "differential.json"
    differential = json.loads(differential_path.read_text())
    if differential.get("cases") != 79 or differential.get("passed") != 79:
        raise RuntimeError("Shadow hybrid differential changed")
    valgrind = {
        name: valgrind_summary(hybrid / f"valgrind-{name}.log", name)
        for name in PROGRAMS
    }

    executable = hybrid / "shadow"
    stripped = hybrid / "shadow.stripped"
    dependencies = re.findall(
        r"Shared library: \[([^]]+)\]",
        (hybrid / "shadow.dynamic").read_text(errors="replace"),
    )
    oracle_path = root / "evidence/shadow-4.20.4-oracle.json"
    normalization_path = root / "evidence/shadow-4.20.4-normalization.json"
    evidence = {
        "schema": 1,
        "release": "4.20.4",
        "recorded_at": "2026-11-24",
        "status": "complete no-hole translation and hybrid parity",
        "input": {
            "compile_commands": 196,
            "compile_database_sha256": sha256(database),
            "closure_sha256": sha256(closure_path),
            "oracle_evidence_sha256": sha256(oracle_path),
            "normalization_evidence_sha256": sha256(normalization_path),
        },
        "translator": {
            "name": "C2Rust",
            "version": "0.22.1",
            "fail_on_error": True,
            "preserve_unused_functions": True,
            "canonical_production_sources": 201,
            "translated_c_sources": 196,
            "excluded_noninstalled_program_sources": closure[
                "excluded_noninstalled_program_sources"
            ],
            "translation_holes": 0,
        },
        "untouched_translation": {**audit_inventory, "cargo_check": raw_cargo},
        "repaired_translation": {
            **nightly_inventory,
            "active_translated_c_sources": 196,
            "canonical_c_sources": [],
            "repair_operations": 21,
            "repair_sites": 22,
            "repair_files": 13,
            "cargo_check": nightly_cargo,
            "native_release_build_success": True,
            "archive": {
                "bytes": archive.stat().st_size,
                "sha256": sha256(archive),
                "entrypoint_definition_counts": entrypoints,
            },
            "repair_manifest_sha256": sha256(repair_path),
        },
        "hybrid": {
            "public_programs": 32,
            "entrypoint_engines": 30,
            "differential": {
                "cases": 79,
                "passed": 79,
                "sha256": sha256(differential_path),
            },
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
        "next_gate": "link all 32 Shadow names into the unified Rustbox multicall",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "hybrid_cases": 79,
        "holes": 0,
        "raw_pointers": nightly_inventory["raw_pointer_type_occurrences"],
        "translated_sources": 196,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
