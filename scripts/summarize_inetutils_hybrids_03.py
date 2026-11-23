#!/usr/bin/env python3
"""Publish evidence for the remaining six Inetutils client hybrids."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


PROGRAMS = ("rcp", "rlogin", "rsh", "ftp", "talk", "telnet")
HOLES = ("compile_error!", "todo!", "unimplemented!", "C2Rust Translation Error")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def needed(binary: Path) -> list[str]:
    output = subprocess.check_output(["readelf", "-d", str(binary)], text=True)
    return sorted(set(re.findall(r"Shared library: \[([^]]+)\]", output)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--hybrid-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.repository.resolve()
    analysis = root / "work/analysis/inetutils-2.8"
    translations = analysis / "program-translations"
    artifacts = analysis / "program-hybrids"
    differential_path = artifacts / "differential-03.json"
    differential = json.loads(differential_path.read_text())
    if differential["applets"] != 6 or differential["cases"] != 33 \
            or differential["passed"] != 33:
        raise RuntimeError("Inetutils remaining-client differential evidence changed")

    programs = {}
    total_sources = 0
    unique_sources: set[str] = set()
    for name in PROGRAMS:
        directory = translations / name
        closure_path = directory / "closure.json"
        closure = json.loads(closure_path.read_text())
        stable = directory / f"{name}-stable"
        rust_sources = sorted(stable.rglob("*.rs"))
        text = "\n".join(path.read_text(encoding="utf-8") for path in rust_sources)
        holes = {term: text.count(term) for term in HOLES}
        if any(holes.values()):
            raise RuntimeError(f"Inetutils {name} translation contains a hole")
        cargo_path = artifacts / f"{name}-cargo-check.json"
        cargo = json.loads(cargo_path.read_text())
        if not cargo["build_finished_success"] or cargo["errors"]:
            raise RuntimeError(f"Inetutils {name} stable crate does not compile")
        binary = args.hybrid_root / name
        symbols_path = artifacts / f"{name}.symbols"
        entrypoint = f"rustbox_inetutils_{name}_main"
        if sum(line.split()[-1:] == [entrypoint]
               for line in symbols_path.read_text().splitlines()) != 1:
            raise RuntimeError(f"Inetutils {name} entrypoint is not unique")
        valgrind_path = artifacts / f"valgrind-{name}.log"
        if "ERROR SUMMARY: 0 errors" not in valgrind_path.read_text(errors="replace"):
            raise RuntimeError(f"Inetutils {name} Valgrind errors")

        boundary_path = stable / "rustbox-inetutils-program-boundary.json"
        boundary = None
        if name == "telnet":
            boundary = json.loads(boundary_path.read_text())
            if boundary["canonical_c_residue"] != "lib/printf-args.c":
                raise RuntimeError("Inetutils telnet ABI boundary changed")
        elif boundary_path.exists():
            raise RuntimeError(f"unexpected Inetutils {name} C boundary")

        total_sources += closure["compile_commands"]
        unique_sources.update(closure["sources"])
        programs[name] = {
            "translated_sources": closure["compile_commands"],
            "sources": closure["sources"],
            "direct_objects": closure.get("direct_objects", []),
            "closure_manifest_sha256": sha256(closure_path),
            "rust_files": len(rust_sources),
            "rust_lines": sum(path.read_text().count("\n") for path in rust_sources),
            "raw_pointer_type_occurrences": len(re.findall(r"\*(?:mut|const)\s+", text)),
            "holes": holes,
            "canonical_c_residue": None if boundary is None else boundary["canonical_c_residue"],
            "boundary_manifest_sha256": None if boundary is None else sha256(boundary_path),
            "cargo_check_sha256": sha256(cargo_path),
            "binary": {
                "bytes": binary.stat().st_size,
                "sha256": sha256(binary),
                "needed": needed(binary),
                "entrypoint": entrypoint,
            },
            "valgrind": {"errors": 0, "log_sha256": sha256(valgrind_path)},
        }

    evidence = {
        "schema": 1,
        "release": "2.8",
        "recorded_at": "2026-11-24",
        "status": "all 16 clients have program-scoped hybrid canonical parity",
        "applets": 6,
        "programs": programs,
        "translation": {
            "program_source_instances": total_sources,
            "unique_sources": len(unique_sources),
            "canonical_c_residue_sources": 1,
            "canonical_c_residue": ["lib/printf-args.c"],
            "holes": 0,
        },
        "tests": {
            "differential_cases": 33,
            "differential_passed": 33,
            "differential_sha256": sha256(differential_path),
            "valgrind_programs": 6,
            "valgrind_errors": 0,
        },
        "scope": {
            "inetutils_clients_with_hybrid_parity": 16,
            "inetutils_daemons_with_hybrid_parity": 0,
            "program_namespaces_are_separate": True,
            "integrated_into_rustbox": False,
        },
        "hardening": {
            "raw_pointers_and_unsafe_are_inventory_only": True,
            "deferred_until_all_applets_complete": True,
        },
        "next_gate": (
            "complete program-scoped hybrid parity for the ten GNU Inetutils "
            "daemons, namespace defined symbols, and integrate all 26"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "applets": 6,
        "cases": 33,
        "program_source_instances": total_sources,
        "unique_sources": len(unique_sources),
        "canonical_c_residue_sources": 1,
        "valgrind_errors": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
