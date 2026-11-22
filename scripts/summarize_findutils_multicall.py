#!/usr/bin/env python3
"""Summarize GNU Findutils integration in the unified Rustbox executable."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "work/analysis/findutils-4.10.0/multicall"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    differential_path = REPORT / "differential.json"
    differential = json.loads(differential_path.read_text())
    if differential["cases"] != 38 or differential["passed"] != 38:
        raise RuntimeError("Findutils unified multicall differential changed")
    valgrind = {}
    for name in ("find", "xargs", "locate", "updatedb"):
        path = REPORT / f"valgrind-{name}.log"
        text = path.read_text(errors="replace")
        if "ERROR SUMMARY: 0 errors" not in text:
            raise RuntimeError(f"Findutils unified {name} Valgrind result changed")
        valgrind[name] = {"errors": 0, "sha256": sha256(path)}
    link_path = ROOT / "work/analysis/rustbox-multicall-link.json"
    link = json.loads(link_path.read_text())
    if link.get("findutils_public_names") != 4:
        raise RuntimeError("Findutils unified linker surface changed")
    evidence = {
        "schema": 1,
        "release": "4.10.0",
        "recorded_at": "2026-11-22",
        "status": "complete unified multicall integration",
        "public_names": ["find", "locate", "updatedb", "xargs"],
        "linked_entrypoints": ["find", "frcode", "locate", "xargs"],
        "updatedb": {
            "implementation": "in-binary C coordinator",
            "pipeline": ["translated find", "translated GNU sort", "translated frcode"],
            "external_script": False,
        },
        "behavior": {
            "canonical_differential": {
                "cases": 38,
                "passed": 38,
                "sha256": sha256(differential_path),
            },
            "valgrind": valgrind,
        },
        "link_report_sha256": sha256(link_path),
        "binary": link["binary"],
        "next_gate": "complete; unified evidence is included in rustbox-multicall.json",
    }
    output = ROOT / "evidence/findutils-4.10.0-multicall.json"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"differential": 38, "public_names": 4, "valgrind": 4}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
