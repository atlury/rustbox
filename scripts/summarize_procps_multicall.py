#!/usr/bin/env python3
"""Publish reproducible Procps-ng unified-multicall integration evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PROGRAMS = (
    "free", "hugetop", "procps-kill", "pgrep", "pidof", "pidwait", "pkill",
    "pmap", "ps", "pwdx", "skill", "slabtop", "snice", "sysctl",
    "tload", "top", "procps-uptime", "vmstat", "w", "watch",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.repository.resolve()
    logs = root / "work/analysis/procps-ng-4.0.7/multicall"
    differential_path = logs / "differential.json"
    link_path = root / "work/analysis/rustbox-multicall-link.json"
    dispatch_path = root / "work/analysis/rustbox-multicall-dispatch.json"
    differential = json.loads(differential_path.read_text())
    link = json.loads(link_path.read_text())
    dispatch = json.loads(dispatch_path.read_text())
    if (
        differential.get("programs") != 20
        or differential.get("cases") != 51
        or differential.get("passed") != 51
        or not all(record.get("passed") for record in differential.get("records", []))
    ):
        raise RuntimeError("Procps multicall differential changed")
    if (
        link.get("procps_programs") != 20
        or link.get("total_dispatch_names") != 413
        or len(link.get("procps_namespaced_symbols", [])) != 422
        or dispatch.get("cases") != 818
        or dispatch.get("passed") != 818
        or dispatch.get("failures")
    ):
        raise RuntimeError("Procps unified dispatcher evidence changed")

    valgrind = {}
    for name in PROGRAMS:
        path = logs / f"valgrind-{name}.log"
        text = path.read_text(errors="replace")
        if name == "sysctl":
            if (
                "definitely lost: 16 bytes in 1 blocks" not in text
                or "ERROR SUMMARY: 1 errors" not in text
            ):
                raise RuntimeError("Procps sysctl canonical baseline changed")
            valgrind[name] = {
                "errors": 1, "definitely_lost_bytes": 16,
                "canonical_baseline": True, "sha256": sha256(path),
            }
            continue
        zero_loss = all(marker in text for marker in (
            "definitely lost: 0 bytes", "indirectly lost: 0 bytes",
            "possibly lost: 0 bytes",
        ))
        if "ERROR SUMMARY: 0 errors" not in text or not (
            "All heap blocks were freed" in text or zero_loss
        ):
            raise RuntimeError(f"Procps multicall Valgrind changed: {name}")
        valgrind[name] = {
            "errors": 0, "retained_bytes": 0, "sha256": sha256(path),
        }

    evidence = {
        "schema": 1,
        "release": "4.0.7",
        "recorded_at": "2026-11-24",
        "status": "all 20 Procps-ng programs integrated into unified Rustbox",
        "programs": list(PROGRAMS),
        "translation": {
            "translated_sources": 49,
            "translated_engines": 17,
            "canonical_c_residue_sources": 0,
            "namespaced_symbols": 422,
        },
        "aliases": {"kill": "procps-kill", "uptime": "procps-uptime"},
        "differential": {
            "cases": 51, "passed": 51, "exact": True,
            "sha256": sha256(differential_path),
        },
        "dispatcher": {
            "global_cases": 818, "global_passed": 818,
            "total_dispatch_names": 413, "sha256": sha256(dispatch_path),
        },
        "valgrind": valgrind,
        "link_report_sha256": sha256(link_path),
        "next_gate": "begin the next incomplete canonical utility suite",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"programs": 20, "cases": 51, "dispatch": 818}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
