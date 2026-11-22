#!/usr/bin/env python3
"""Summarize GNU Findutils translated-hybrid parity evidence."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "work/analysis/findutils-4.10.0"
HYBRID = ANALYSIS / "hybrid"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    differential = json.loads((HYBRID / "differential.json").read_text())
    if differential["cases"] != 38 or differential["passed"] != 38:
        raise RuntimeError("Findutils hybrid differential changed")
    residue = json.loads((HYBRID / "c-residue.json").read_text())
    sources = [record["source"] for record in residue["sources"]]
    expected = ["gl/lib/printf-args.c", "gl/lib/printf-parse.c", "gl/lib/vasnprintf.c"]
    if sources != expected:
        raise RuntimeError("Findutils hybrid C residue changed")
    programs = {
        "find": "find/find", "xargs": "xargs/xargs",
        "locate": "locate/locate", "frcode": "locate/frcode",
    }
    binaries = {}
    for name, relative in programs.items():
        path = Path("/rustbox-findutils/hybrid") / relative
        section_log = HYBRID / f"{name}.sections"
        symbols = (HYBRID / f"{name}.symbols").read_text(errors="replace")
        entry = f"rustbox_{name}_main"
        if len(re.findall(rf"\b{entry}$", symbols, re.MULTILINE)) != 1:
            raise RuntimeError(f"Findutils hybrid {name} entrypoint changed")
        valgrind = (HYBRID / f"valgrind-{name}.log").read_text(errors="replace")
        if "ERROR SUMMARY: 0 errors" not in valgrind:
            raise RuntimeError(f"Findutils hybrid {name} Valgrind changed")
        binaries[name] = {
            "container_path": str(path),
            "sections_sha256": sha256(section_log),
            "symbols_sha256": sha256(HYBRID / f"{name}.symbols"),
            "valgrind_errors": 0,
        }
    evidence = {
        "schema": 1,
        "release": "4.10.0",
        "recorded_at": "2026-11-22",
        "status": "complete translated-hybrid parity",
        "scope": {
            "public_names": ["find", "xargs", "locate", "updatedb"],
            "translated_entrypoints": ["find", "xargs", "locate", "frcode"],
        },
        "rust_archive_evidence_sha256": sha256(ROOT / "evidence/findutils-4.10.0-c2rust.json"),
        "canonical_c_abi_residue": {
            "sources": expected,
            "objects": 3,
            "manifest_sha256": sha256(HYBRID / "c-residue.json"),
            "reason": "preserve x86_64 SysV C long double variadic ABI",
        },
        "behavior": {
            "canonical_differential": {
                "cases": 38, "passed": 38,
                "sha256": sha256(HYBRID / "differential.json"),
            },
            "valgrind": {name: {"errors": 0} for name in programs},
        },
        "binaries": binaries,
        "next_gate": "unified Rustbox multicall integration",
    }
    output = ROOT / "evidence/findutils-4.10.0-hybrid.json"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"differential": 38, "programs": 4, "valgrind": 4}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
