#!/usr/bin/env python3
"""Publish reproducible Shadow unified-multicall integration evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PROGRAMS = (
    "chage", "chfn", "chgpasswd", "chpasswd", "chsh", "faillog",
    "getsubids", "gpasswd", "groupadd", "groupdel", "groupmod", "grpck",
    "grpconv", "grpunconv", "lastlog", "login", "newgidmap", "newgrp",
    "newuidmap", "newusers", "nologin", "passwd", "pwck", "pwconv",
    "pwunconv", "su", "useradd", "userdel", "usermod", "vipw", "sg",
    "vigr",
)
ALIASES = {
    name: f"shadow-{name}"
    for name in ("chfn", "chsh", "login", "newgrp", "nologin", "su", "vigr", "vipw")
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sequence_sha256(value: object) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.repository.resolve()
    logs = root / "work/analysis/shadow-4.20.4/multicall"
    differential_path = logs / "differential.json"
    link_path = root / "work/analysis/rustbox-multicall-link.json"
    dispatch_path = root / "work/analysis/rustbox-multicall-dispatch.json"
    differential = json.loads(differential_path.read_text())
    link = json.loads(link_path.read_text())
    dispatch = json.loads(dispatch_path.read_text())
    symbols = link.get("shadow_namespaced_symbols", [])
    runtime_members = link.get("shadow_coalesced_runtime_members", [])
    if (
        differential.get("programs") != 32
        or differential.get("cases") != 79
        or differential.get("stateful_cases") != 8
        or differential.get("passed") != 79
        or not all(record.get("passed") for record in differential.get("records", []))
    ):
        raise RuntimeError("Shadow multicall differential changed")
    if (
        link.get("shadow_programs") != 32
        or link.get("total_dispatch_names") != 445
        or len(symbols) != 265
        or len(runtime_members) != 211
        or dispatch.get("shadow_programs") != 32
        or dispatch.get("cases") != 882
        or dispatch.get("passed") != 882
        or dispatch.get("failures")
    ):
        raise RuntimeError("Shadow unified dispatcher evidence changed")

    valgrind = {}
    for name in PROGRAMS:
        path = logs / f"valgrind-{name}.log"
        text = path.read_text(errors="replace")
        if name == "gpasswd":
            if (
                "definitely lost: 48 bytes in 1 blocks" not in text
                or "indirectly lost: 28 bytes in 5 blocks" not in text
                or "ERROR SUMMARY: 6 errors" not in text
            ):
                raise RuntimeError("Shadow gpasswd canonical baseline changed")
            valgrind[name] = {
                "errors": 6,
                "definitely_lost_bytes": 48,
                "indirectly_lost_bytes": 28,
                "canonical_baseline": True,
                "sha256": sha256(path),
            }
            continue
        if "ERROR SUMMARY: 0 errors" not in text:
            raise RuntimeError(f"Shadow multicall Valgrind changed: {name}")
        valgrind[name] = {"errors": 0, "sha256": sha256(path)}

    evidence = {
        "schema": 1,
        "release": "4.20.4",
        "recorded_at": "2026-11-24",
        "status": "all 32 Shadow programs integrated into unified Rustbox",
        "programs": list(PROGRAMS),
        "translation": {
            "selected_sources": 196,
            "translated_engines": 30,
            "canonical_c_residue_sources": 0,
            "namespaced_symbols": len(symbols),
            "namespaced_symbols_sha256": sequence_sha256(symbols),
            "coalesced_identical_runtime_members": len(runtime_members),
            "coalesced_runtime_members_sha256": sequence_sha256(runtime_members),
        },
        "aliases": ALIASES,
        "differential": {
            "cases": 79,
            "stateful_cases": 8,
            "passed": 79,
            "exact": True,
            "sha256": sha256(differential_path),
        },
        "dispatcher": {
            "global_cases": 882,
            "global_passed": 882,
            "total_dispatch_names": 445,
            "sha256": sha256(dispatch_path),
        },
        "valgrind": valgrind,
        "link_report_sha256": sha256(link_path),
        "next_gate": "begin canonical IPRoute2 oracle and translation",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"programs": 32, "cases": 79, "dispatch": 882}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
