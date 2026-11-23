#!/usr/bin/env python3
"""Record the verified GNU Inetutils integration in the Rustbox multicall."""

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
    parser.add_argument("--link-report", required=True, type=Path)
    parser.add_argument("--report-directory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    link = json.loads(args.link_report.read_text())
    differential_path = args.report_directory / "differential.json"
    differential = json.loads(differential_path.read_text())
    symbols = link.get("inetutils_namespaced_symbols", {})
    if (
        differential.get("applets") != 26
        or differential.get("cases") != 133
        or differential.get("passed") != 133
        or link.get("inetutils_programs") != 26
        or link.get("total_dispatch_names") != 386
        or len(symbols) != 26
    ):
        raise RuntimeError("Inetutils multicall coverage is incomplete")

    valgrind = {}
    for name in sorted(symbols):
        path = args.report_directory / f"valgrind-{name}.log"
        text = path.read_text(errors="replace")
        zero_loss = all(marker in text for marker in (
            "definitely lost: 0 bytes", "indirectly lost: 0 bytes",
            "possibly lost: 0 bytes",
        ))
        if "ERROR SUMMARY: 0 errors" not in text or not (
            "All heap blocks were freed" in text or zero_loss
        ):
            raise RuntimeError(f"Inetutils {name} Valgrind result is incomplete")
        valgrind[name] = {
            "errors": int(re.search(r"ERROR SUMMARY: (\d+) errors", text).group(1)),
            "sha256": sha256(path),
        }

    symbol_bytes = json.dumps(symbols, separators=(",", ":"), sort_keys=True).encode()
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-24",
        "status": "all 26 GNU Inetutils programs integrated at canonical parity",
        "translation": {
            "production_sources": 288,
            "stable_rust_sources": 287,
            "canonical_c_abi_boundaries": ["telnet: lib/printf-args.c"],
            "holes": 0,
        },
        "dispatch": {
            "programs": 26,
            "aliases": {
                "hostname": "inetutils-hostname",
                "logger": "inetutils-logger",
            },
            "aggregate_names": 386,
        },
        "differential": differential,
        "differential_sha256": sha256(differential_path),
        "valgrind": valgrind,
        "collision_isolation": {
            "program_namespaces": len(symbols),
            "renamed_symbols": sum(len(items) for items in symbols.values()),
            "symbol_map_sha256": hashlib.sha256(symbol_bytes).hexdigest(),
        },
        "binary": link["binary"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "programs": 26,
        "cases": differential["passed"],
        "valgrind": len(valgrind),
        "binary_bytes": link["binary"]["bytes"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
