#!/usr/bin/env python3
"""Generate evidence for defined-storage GNU Gawk normalization."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NORMALIZED = ROOT / "work/analysis/gawk-5.4.0/normalized"
ORACLE = ROOT / "work/analysis/gawk-5.4.0/oracle"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_suite(compiler: str) -> dict[str, object]:
    path = NORMALIZED / f"{compiler}-check.log"
    text = path.read_text(errors="replace")
    fatal = re.findall(
        r"^make(?:\[\d+\])?: \*\*\* \[[^]]+: ([^]]+)\] Error \d+$",
        text, re.MULTILINE,
    )
    if fatal != ["pma", "pma-tests", "check-recursive", "check"]:
        raise RuntimeError(f"normalized {compiler} fatal test set changed")
    if (
        text.count("Segmentation fault") != 1
        or text.count("GAWK_PERSIST_FILE=test.pma") != 1
        or "runtime error:" in text
        or "ERROR: AddressSanitizer" in text
        or " differ:" in text
    ):
        raise RuntimeError(f"normalized {compiler} suite changed")
    return {"log_sha256": sha256(path), "pma_virtualization_failures": 1,
            "runtime_diagnostics": 0, "output_differences": 0}


def main() -> int:
    manifest_path = ROOT / "work/analysis/gawk-5.4.0/normalization-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest["changed_sources"] != ["extension/readdir.c", "main.c"]:
        raise RuntimeError("GNU Gawk normalization source set changed")

    compilers = {}
    for compiler in ("gcc", "clang", "sanitizer"):
        database_path = NORMALIZED / f"{compiler}-compile-commands.json"
        database = json.loads(database_path.read_text())
        sources = {record["file"] for record in database}
        if len(database) != 55 or len(sources) != 55:
            raise RuntimeError(f"normalized {compiler} compile closure changed")
        oracle_prefix = str(ORACLE / f"{compiler}-root")
        normalized_prefix = str(NORMALIZED / f"{compiler}-root")
        oracle_paths = [line.removeprefix(oracle_prefix) for line in
                        (ORACLE / f"{compiler}-installed-files.txt").read_text().splitlines()]
        normalized_paths = [line.removeprefix(normalized_prefix) for line in
                            (NORMALIZED / f"{compiler}-installed-files.txt").read_text().splitlines()]
        if oracle_paths != normalized_paths:
            raise RuntimeError(f"normalized {compiler} installed surface changed")
        compilers[compiler] = {
            "compile_actions": len(database), "production_sources": len(sources),
            "compile_database_sha256": sha256(database_path),
            "suite": validate_suite(compiler),
        }

    differentials = {}
    for compiler in ("gcc", "clang"):
        path = NORMALIZED / f"{compiler}-differential.json"
        result = json.loads(path.read_text())
        if result["cases"] != 26 or result["passed"] != 26:
            raise RuntimeError(f"normalized {compiler} differential changed")
        differentials[compiler] = {"cases": 26, "passed": 26, "sha256": sha256(path)}

    valgrind = {}
    for label in ("help", "version"):
        path = NORMALIZED / f"valgrind-{label}.log"
        text = path.read_text(errors="replace")
        if "ERROR SUMMARY: 0 errors" not in text or not all(item in text for item in (
            "definitely lost: 0 bytes", "indirectly lost: 0 bytes", "possibly lost: 0 bytes",
        )):
            raise RuntimeError(f"normalized Gawk {label} Valgrind result changed")
        valgrind[label] = {"errors": 0, "log_sha256": sha256(path)}

    binary = NORMALIZED / "gcc-root/usr/bin/gawk"
    symbols = subprocess.run(["nm", "-g", str(binary)], check=True, text=True,
                             stdout=subprocess.PIPE).stdout
    if not re.search(r"\bT rustbox_gawk_main$", symbols, re.MULTILINE):
        raise RuntimeError("normalized Gawk multicall entrypoint is not exported")
    if not re.search(r"\bT main$", symbols, re.MULTILINE):
        raise RuntimeError("normalized Gawk standalone wrapper is missing")

    evidence = {
        "schema": 1,
        "release": "5.4.0",
        "recorded_at": "2026-11-22",
        "status": "complete deterministic defined-storage and multicall normalization",
        "manifest": manifest,
        "manifest_sha256": sha256(manifest_path),
        "scope": {
            "production_sources": 55,
            "changed_sources": manifest["changed_sources"],
            "translated_entrypoints": ["gawk"],
            "public_names": ["gawk", "awk", "gawkbug"],
            "extensions": 12,
        },
        "compilers": compilers,
        "behavior": {
            "canonical_differentials": differentials,
            "sanitizer": {
                "address_errors": 0, "undefined_behavior_diagnostics": 0,
                "canonical_readdir_bounds_defect_removed": True,
            },
            "valgrind": valgrind,
        },
        "entrypoint": {"symbol": "rustbox_gawk_main", "standalone_wrapper": True},
        "next_gate": "probe the exact production closure with C2Rust",
    }
    output = ROOT / "evidence/gawk-5.4.0-normalization.json"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "changed_sources": 2, "differential": 52, "entrypoints": 1,
        "production_sources": 55, "ubsan": 0, "valgrind": 2,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
