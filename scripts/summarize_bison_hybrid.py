#!/usr/bin/env python3
"""Publish reproducible GNU Bison hybrid executable evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.repository.resolve()
    analysis = root / "work/analysis/bison-3.8.2"
    logs = analysis / "hybrid"
    artifacts = analysis / "hybrid-artifacts"
    binary = artifacts / "bison"
    stripped = artifacts / "bison.stripped"

    differential = json.loads((logs / "differential.json").read_text())
    if differential["cases"] != 12 or differential["passed"] != 12:
        raise RuntimeError("Bison hybrid differential changed")
    yacc = json.loads((logs / "yacc-frontend.json").read_text())
    if not yacc["passed"] or yacc["compile_status"] != 0 or yacc["runtime_status"] != 0:
        raise RuntimeError("Bison yacc frontend parity failed")
    residue = json.loads((artifacts / "c-residue/manifest.json").read_text())
    expected = [
        "lib/printf-args.c", "lib/printf-frexpl.c",
        "lib/printf-parse.c", "lib/vasnprintf.c",
    ]
    if [record["source"] for record in residue["sources"]] != expected:
        raise RuntimeError("Bison hybrid C residue changed")
    symbols = (logs / "bison.symbols").read_text()
    counts = {
        name: len(re.findall(rf"\b{name}$", symbols, re.MULTILINE))
        for name in ("rustbox_bison_main", "rustbox_yacc_main")
    }
    if set(counts.values()) != {1}:
        raise RuntimeError(f"Bison hybrid entrypoint definitions changed: {counts}")
    valgrind = (logs / "valgrind-help.log").read_text(errors="replace")
    for marker in (
        "ERROR SUMMARY: 0 errors", "definitely lost: 0 bytes in 0 blocks",
        "indirectly lost: 0 bytes in 0 blocks", "possibly lost: 0 bytes in 0 blocks",
    ):
        if marker not in valgrind:
            raise RuntimeError(f"Bison hybrid Valgrind marker missing: {marker}")
    needed = re.findall(r"Shared library: \[([^]]+)\]", (logs / "bison.dynamic").read_text())
    evidence = {
        "schema": 1,
        "release": "3.8.2",
        "recorded_at": "2026-11-23",
        "status": "full C/C++ Bison hybrid at canonical generated-parser parity",
        "frontends": ["bison", "yacc"],
        "hybrid": {
            "translated_rust_sources": 148,
            "canonical_c_sources": expected,
            "binary": {
                "bytes": binary.stat().st_size,
                "sha256": sha256(binary),
                "stripped_bytes": stripped.stat().st_size,
                "stripped_sha256": sha256(stripped),
                "dynamic_needed": needed,
                "entrypoint_definition_counts": counts,
            },
            "residue_manifest_sha256": sha256(artifacts / "c-residue/manifest.json"),
        },
        "differential": {
            "cases": differential["cases"],
            "compiled_parsers": differential["compiled_parsers"],
            "passed": differential["passed"],
            "sha256": sha256(logs / "differential.json"),
            "coverage": [
                "CLI diagnostics", "C pull", "C push", "C GLR",
                "C++ LALR", "C++ GLR", "C++ GLR2", "POSIX yacc",
                "text report", "Graphviz", "XML",
            ],
        },
        "yacc_frontend": {**yacc, "sha256": sha256(logs / "yacc-frontend.json")},
        "valgrind": {
            "errors": 0,
            "definitely_lost_bytes": 0,
            "indirectly_lost_bytes": 0,
            "possibly_lost_bytes": 0,
            "sha256": sha256(logs / "valgrind-help.log"),
        },
        "runtime_boundary": {
            "current": ["external GNU M4", "external C/C++ skeleton data directory"],
            "next": [
                "route M4 through Rustbox's GNU M4 applet",
                "embed and materialize the required C/C++ skeleton resources",
                "link both frontends into the unified multicall",
            ],
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "differential": differential["passed"],
        "frontends": 2,
        "residue_sources": len(expected),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
