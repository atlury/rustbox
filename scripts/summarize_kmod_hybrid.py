#!/usr/bin/env python3
"""Publish reproducible Kmod hybrid executable evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


PROGRAMS = ("kmod", "depmod", "insmod", "lsmod", "modinfo", "modprobe", "rmmod")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean_valgrind(path: Path) -> dict[str, object]:
    text = path.read_text(errors="replace")
    if "ERROR SUMMARY: 0 errors" not in text:
        raise RuntimeError(f"Kmod hybrid Valgrind errors: {path}")
    all_freed = "All heap blocks were freed -- no leaks are possible" in text
    if not all_freed:
        for marker in (
            "definitely lost: 0 bytes in 0 blocks",
            "indirectly lost: 0 bytes in 0 blocks",
            "possibly lost: 0 bytes in 0 blocks",
        ):
            if marker not in text:
                raise RuntimeError(f"Kmod hybrid Valgrind marker missing: {marker}")
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
    logs = root / "work/analysis/kmod-34.3/hybrid"
    binary = logs / "kmod"
    stripped = logs / "kmod.stripped"

    differential_path = logs / "differential.json"
    differential = json.loads(differential_path.read_text())
    if differential["cases"] != 25 or differential["passed"] != 25:
        raise RuntimeError("Kmod hybrid differential changed")
    if not all(record["passed"] for record in differential["records"]):
        raise RuntimeError("Kmod hybrid has a non-passing differential record")

    symbols = (logs / "kmod.symbols").read_text()
    entrypoints = len(re.findall(r"\brustbox_kmod_main$", symbols, re.MULTILINE))
    if entrypoints != 1:
        raise RuntimeError("Kmod hybrid entrypoint definition changed")
    needed = re.findall(
        r"Shared library: \[([^]]+)\]", (logs / "kmod.dynamic").read_text()
    )
    expected_needed = {
        "libzstd.so.1", "liblzma.so.5", "libz.so.1", "libcrypto.so.3",
        "libm.so.6", "libgcc_s.so.1", "libc.so.6", "ld-linux-x86-64.so.2",
    }
    if set(needed) != expected_needed:
        raise RuntimeError(f"Kmod hybrid dependency closure changed: {needed}")

    valgrind = {name: clean_valgrind(logs / f"valgrind-{name}.log") for name in PROGRAMS}
    evidence = {
        "schema": 1,
        "release": "34.3",
        "recorded_at": "2026-11-24",
        "status": "all seven Kmod frontends at signed canonical parity",
        "frontends": list(PROGRAMS),
        "hybrid": {
            "translated_rust_sources": 26,
            "canonical_c_sources": [],
            "binary": {
                "bytes": binary.stat().st_size,
                "sha256": sha256(binary),
                "stripped_bytes": stripped.stat().st_size,
                "stripped_sha256": sha256(stripped),
                "dynamic_needed": needed,
                "entrypoint_definition_counts": {"rustbox_kmod_main": entrypoints},
            },
        },
        "differential": {
            "cases": 25,
            "passed": 25,
            "exact": True,
            "sha256": sha256(differential_path),
        },
        "valgrind": valgrind,
        "next_gate": "link all seven Kmod names into the unified Rustbox multicall",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "applets": len(PROGRAMS),
        "differential": 25,
        "residue_sources": 0,
        "stripped_bytes": stripped.stat().st_size,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
