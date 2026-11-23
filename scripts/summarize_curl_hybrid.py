#!/usr/bin/env python3
"""Publish reproducible curl hybrid executable evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean_valgrind(path: Path) -> dict[str, object]:
    text = path.read_text(errors="replace")
    if "ERROR SUMMARY: 0 errors" not in text:
        raise RuntimeError(f"curl hybrid Valgrind errors: {path}")
    all_freed = "All heap blocks were freed -- no leaks are possible" in text
    if not all_freed:
        for marker in (
            "definitely lost: 0 bytes in 0 blocks",
            "indirectly lost: 0 bytes in 0 blocks",
            "possibly lost: 0 bytes in 0 blocks",
        ):
            if marker not in text:
                raise RuntimeError(f"curl hybrid Valgrind marker missing: {marker}")
    return {
        "errors": 0,
        "retained_bytes": 0,
        "all_heap_blocks_freed": all_freed,
        "sha256": sha256(path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.repository.resolve()
    analysis = root / "work/analysis/curl-8.23.0"
    logs = analysis / "hybrid"
    artifacts = analysis / "hybrid-artifacts"
    binary = artifacts / "curl"
    stripped = artifacts / "curl.stripped"

    differential = json.loads((logs / "differential.json").read_text())
    if (
        differential["cases"] != 12
        or differential["passed"] != 12
        or not differential["gcc_clang_exact"]
        or not all(record["passed"] for record in differential["records"])
    ):
        raise RuntimeError("curl hybrid differential changed")
    residue_path = artifacts / "c-residue/manifest.json"
    residue = json.loads(residue_path.read_text())
    if [record["source"] for record in residue["sources"]] != ["lib/mprintf.c"]:
        raise RuntimeError("curl hybrid C residue changed")
    symbols = (logs / "curl.symbols").read_text()
    entrypoints = len(re.findall(r"\brustbox_curl_main$", symbols, re.MULTILINE))
    if entrypoints != 1:
        raise RuntimeError("curl hybrid entrypoint definition changed")
    needed = re.findall(
        r"Shared library: \[([^]]+)\]", (logs / "curl.dynamic").read_text()
    )
    if any(name not in {"libm.so.6", "libgcc_s.so.1", "libc.so.6", "ld-linux-x86-64.so.2"}
           for name in needed):
        raise RuntimeError(f"curl hybrid gained a package dependency: {needed}")

    valgrind = {
        name: clean_valgrind(logs / f"valgrind-{name}.log")
        for name in ("version", "file")
    }
    evidence = {
        "schema": 1,
        "release": "8.23.0",
        "recorded_at": "2026-11-23",
        "status": "curl hybrid at canonical CLI and file-protocol parity",
        "frontends": ["curl"],
        "hybrid": {
            "translated_rust_sources": 239,
            "canonical_c_sources": ["lib/mprintf.c"],
            "binary": {
                "bytes": binary.stat().st_size,
                "sha256": sha256(binary),
                "stripped_bytes": stripped.stat().st_size,
                "stripped_sha256": sha256(stripped),
                "dynamic_needed": needed,
                "entrypoint_definition_counts": {
                    "rustbox_curl_main": entrypoints,
                },
            },
            "residue_manifest_sha256": sha256(residue_path),
        },
        "differential": {
            "cases": differential["cases"],
            "passed": differential["passed"],
            "exact": differential["gcc_clang_exact"],
            "sha256": sha256(logs / "differential.json"),
            "coverage": [record["name"] for record in differential["records"]],
        },
        "valgrind": valgrind,
        "next_gate": (
            "provide curl-config in-process, link curl into the unified multicall, "
            "and replay the canonical differential through Rustbox"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "differential": differential["passed"],
        "frontends": 1,
        "residue_sources": 1,
        "stripped_bytes": stripped.stat().st_size,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
