#!/usr/bin/env python3
"""Validate the deterministic GNU Bison multicall-entry normalization."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "work/analysis/bison-3.8.2"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_files(path: Path, prefix: Path) -> list[str]:
    return [line.removeprefix(str(prefix)) for line in path.read_text().splitlines()]


def leak_signature(path: Path) -> dict[str, int]:
    text = path.read_text(errors="replace")
    error = re.search(r"ERROR SUMMARY: (\d+) errors", text)
    if not error or int(error.group(1)) != 0:
        raise RuntimeError(f"Valgrind errors changed: {path}")
    result = {"errors": 0}
    for key, pattern in (
        ("definitely_lost_bytes", r"definitely lost: ([0-9,]+) bytes"),
        ("indirectly_lost_bytes", r"indirectly lost: ([0-9,]+) bytes"),
        ("possibly_lost_bytes", r"possibly lost: ([0-9,]+) bytes"),
    ):
        match = re.search(pattern, text)
        result[key] = 0 if not match else int(match.group(1).replace(",", ""))
    return result


def main() -> int:
    manifest_path = ANALYSIS / "normalization-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest["changed_sources"] != ["src/main.c"]:
        raise RuntimeError("Bison normalization source set changed")
    if manifest["entrypoint"] != "rustbox_bison_main":
        raise RuntimeError("Bison normalized entrypoint changed")

    normalized = ANALYSIS / "normalized"
    log = normalized / "clang-check.log"
    text = log.read_text(errors="replace")
    successful = re.search(r"^(\d+) tests were successful\.$", text, re.MULTILINE)
    skipped = re.search(r"^(\d+) tests were skipped\.$", text, re.MULTILINE)
    if not successful or not skipped or (
        int(successful.group(1)), int(skipped.group(1))
    ) != (712, 64):
        raise RuntimeError("Bison normalized upstream suite changed")

    differential = json.loads((normalized / "canonical-differential.json").read_text())
    if differential["cases"] != 12 or differential["passed"] != 12:
        raise RuntimeError("Bison normalized differential is incomplete")

    database_path = normalized / "clang-compile-commands.json"
    database = json.loads(database_path.read_text())
    sources = sorted({record["file"] for record in database})
    if len(database) != 154 or len(sources) != 154:
        raise RuntimeError("Bison normalized compile closure changed")
    if sum(source.endswith(("/lib/main.c", "/lib/yyerror.c")) for source in sources) != 2:
        raise RuntimeError("Bison normalized liby closure changed")

    canonical_root = ANALYSIS / "oracle/gcc-root"
    normalized_root = normalized / "clang-root"
    canonical_files = normalized_files(
        ANALYSIS / "oracle/gcc-installed-files.txt", canonical_root
    )
    staged_files = normalized_files(
        normalized / "clang-installed-files.txt", normalized_root
    )
    if canonical_files != staged_files:
        raise RuntimeError("Bison normalized installed surface changed")

    binary = normalized_root / "usr/bin/bison"
    symbols = subprocess.run(
        ["nm", "-g", "--defined-only", str(binary)], check=True, text=True,
        stdout=subprocess.PIPE,
    ).stdout.splitlines()
    if sum(line.split()[-1:] == ["rustbox_bison_main"] for line in symbols) != 1:
        raise RuntimeError("Bison normalized entrypoint symbol is absent")
    if sum(line.split()[-1:] == ["main"] for line in symbols) != 1:
        raise RuntimeError("Bison normalized standalone wrapper is absent")

    valgrind = {}
    for label in ("help", "version"):
        canonical = leak_signature(ANALYSIS / f"oracle/valgrind-{label}.log")
        staged = leak_signature(normalized / f"valgrind-{label}.log")
        if canonical != staged:
            raise RuntimeError(f"Bison {label} ownership signature changed")
        valgrind[label] = {
            **staged,
            "canonical_log_sha256": sha256(ANALYSIS / f"oracle/valgrind-{label}.log"),
            "normalized_log_sha256": sha256(normalized / f"valgrind-{label}.log"),
        }

    evidence = {
        "schema": 1,
        "release": "3.8.2",
        "recorded_at": "2026-11-23",
        "manifest": manifest,
        "upstream_suite": {
            "successful": 712,
            "skipped": 64,
            "total": 776,
            "log_sha256": sha256(log),
        },
        "canonical_differential": differential,
        "compile_database": {
            "commands": len(database),
            "sources": len(sources),
            "bison_production_sources": 152,
            "liby_sources": 2,
            "sha256": sha256(database_path),
        },
        "installed_files": len(staged_files),
        "symbols": ["main", "rustbox_bison_main"],
        "valgrind": valgrind,
        "binary": {"bytes": binary.stat().st_size, "sha256": sha256(binary)},
        "repairs": [],
    }
    output = ROOT / "evidence/bison-3.8.2-normalization.json"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "changed_sources": manifest["changed_sources"],
        "differential": differential["passed"],
        "production_sources": 152,
        "upstream_tests": 712,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
