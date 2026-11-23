#!/usr/bin/env python3
"""Validate curl's deterministic multicall-entry normalization."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "work/analysis/curl-8.23.0"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def valgrind_signature(path: Path) -> dict[str, int]:
    text = path.read_text(errors="replace")
    error = re.search(r"ERROR SUMMARY: (\d+) errors", text)
    retained = re.search(r"in use at exit: ([0-9,]+) bytes", text)
    if error is None or retained is None:
        raise RuntimeError(f"incomplete curl Valgrind log: {path}")
    result = {
        "errors": int(error.group(1)),
        "bytes_in_use_at_exit": int(retained.group(1).replace(",", "")),
    }
    if result != {"errors": 0, "bytes_in_use_at_exit": 0}:
        raise RuntimeError(f"curl ownership signature changed: {path}: {result}")
    return result


def main() -> int:
    manifest_path = ANALYSIS / "normalization-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest["changed_sources"] != ["src/tool_main.c"]:
        raise RuntimeError("curl normalization source set changed")
    if manifest["entrypoint"] != "rustbox_curl_main":
        raise RuntimeError("curl normalized entrypoint changed")

    normalized = ANALYSIS / "normalized"
    test_log = normalized / "clang-test.log"
    test_text = test_log.read_text(errors="replace")
    considered = re.search(r"TESTDONE: (\d+) tests were considered", test_text)
    passed = re.search(r"TESTDONE: (\d+) tests out of (\d+) reported OK", test_text)
    if considered is None or passed is None:
        raise RuntimeError("curl normalized upstream totals are missing")
    test_totals = tuple(map(int, (considered.group(1), passed.group(1), passed.group(2))))
    if test_totals != (2138, 1601, 1601):
        raise RuntimeError(f"curl normalized upstream suite changed: {test_totals}")

    differential_path = normalized / "canonical-differential.json"
    differential = json.loads(differential_path.read_text())
    if differential["cases"] != 12 or differential["passed"] != 12:
        raise RuntimeError("curl normalized differential is incomplete")

    database_path = normalized / "clang-compile-commands.json"
    database = json.loads(database_path.read_text())
    sources = {record["file"] for record in database}
    unit_actions = sum(
        "-DUNITTESTS" in record["arguments"] for record in database
    )
    if (len(database), len(sources), unit_actions) != (477, 240, 237):
        raise RuntimeError("curl normalized compile closure changed")

    binary = normalized / "curl-clang"
    symbols = subprocess.run(
        ["nm", "-g", "--defined-only", str(binary)], check=True, text=True,
        stdout=subprocess.PIPE,
    ).stdout.splitlines()
    for symbol in ("main", "rustbox_curl_main"):
        if sum(line.split()[-1:] == [symbol] for line in symbols) != 1:
            raise RuntimeError(f"curl normalized symbol is absent: {symbol}")

    oracle = ANALYSIS / "oracle"
    for generated in ("tool_ca_embed", "tool_hugehelp"):
        canonical = oracle / f"{generated}-gcc.c"
        staged = normalized / f"{generated}-clang.c"
        if canonical.read_bytes() != staged.read_bytes():
            raise RuntimeError(f"curl generated source changed: {generated}")

    valgrind = {}
    for label in ("version", "file"):
        canonical_path = oracle / f"valgrind-{label}.log"
        normalized_path = normalized / f"valgrind-{label}.log"
        canonical = valgrind_signature(canonical_path)
        staged = valgrind_signature(normalized_path)
        if canonical != staged:
            raise RuntimeError(f"curl {label} ownership signature changed")
        valgrind[label] = {
            **staged,
            "canonical_log_sha256": sha256(canonical_path),
            "normalized_log_sha256": sha256(normalized_path),
        }

    dynamic = (normalized / "curl-clang.dynamic").read_text(errors="replace")
    needed = re.findall(r"Shared library: \[([^]]+)\]", dynamic)
    if needed != ["libc.so.6"]:
        raise RuntimeError(f"curl normalized runtime closure changed: {needed}")

    evidence = {
        "schema": 1,
        "release": "8.23.0",
        "recorded_at": "2026-11-23",
        "manifest": manifest,
        "upstream_suite": {
            "considered": 2138,
            "applicable": 1601,
            "passed": 1601,
            "log_sha256": sha256(test_log),
        },
        "canonical_differential": differential,
        "compile_database": {
            "commands": len(database),
            "sources": len(sources),
            "production_actions": len(database) - unit_actions,
            "unit_test_variant_actions": unit_actions,
            "sha256": sha256(database_path),
        },
        "symbols": ["main", "rustbox_curl_main"],
        "valgrind": valgrind,
        "binary": {
            "bytes": binary.stat().st_size,
            "sha256": sha256(binary),
            "needed": needed,
        },
        "static_libcurl": {
            "bytes": (normalized / "libcurl-clang.a").stat().st_size,
            "sha256": sha256(normalized / "libcurl-clang.a"),
        },
        "generated_sources": {
            name: sha256(normalized / f"{name}-clang.c")
            for name in ("tool_ca_embed", "tool_hugehelp")
        },
        "repairs": [],
        "next_gate": "strict no-hole C2Rust translation of 240 production sources",
    }
    output = ROOT / "evidence/curl-8.23.0-normalization.json"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "changed_sources": manifest["changed_sources"],
        "differential": differential["passed"],
        "production_sources": len(sources),
        "upstream_tests": 1601,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
