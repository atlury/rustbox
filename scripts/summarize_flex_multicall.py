#!/usr/bin/env python3
"""Publish evidence for Flex's unified Rustbox integration."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "work/analysis/flex-2.6.4/multicall"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    differential_path = REPORTS / "differential.json"
    frontends_path = REPORTS / "frontends.json"
    upstream_path = REPORTS / "upstream-tests.log"
    differential = json.loads(differential_path.read_text())
    frontends = json.loads(frontends_path.read_text())
    if differential["cases"] != 14 or differential["passed"] != 14:
        raise RuntimeError("Flex multicall differential is incomplete")
    if frontends["cases"] != 3 or frontends["passed"] != 3:
        raise RuntimeError("Flex multicall frontend differential is incomplete")

    upstream = upstream_path.read_text(errors="replace")
    counts = {}
    for label in ("TOTAL", "PASS", "SKIP", "XFAIL", "FAIL", "XPASS", "ERROR"):
        match = re.search(rf"^# {label}:\s+(\d+)$", upstream, re.MULTILINE)
        if not match:
            raise RuntimeError(f"Flex multicall suite lacks {label}")
        counts[label.lower()] = int(match.group(1))
    if counts != {
        "total": 114, "pass": 114, "skip": 0, "xfail": 0,
        "fail": 0, "xpass": 0, "error": 0,
    }:
        raise RuntimeError(f"Flex multicall suite changed: {counts}")

    valgrind = {}
    for name in ("flex-version", "flex++-version", "lex-version", "flex-invalid"):
        path = REPORTS / f"valgrind-{name}.log"
        text = path.read_text(errors="replace")
        required = (
            "ERROR SUMMARY: 0 errors", "definitely lost: 0 bytes",
            "indirectly lost: 0 bytes", "possibly lost: 0 bytes",
        )
        if not all(item in text for item in required):
            raise RuntimeError(f"Flex multicall resource check changed: {name}")
        valgrind[name] = {"errors": 0, "lost_bytes": 0, "log_sha256": sha256(path)}

    link_path = ROOT / "work/analysis/rustbox-multicall-link.json"
    dispatch_path = ROOT / "work/analysis/rustbox-multicall-dispatch.json"
    link = json.loads(link_path.read_text())
    dispatch = json.loads(dispatch_path.read_text())
    if link["total_dispatch_names"] != 356 or link["flex_public_names"] != 3:
        raise RuntimeError("Flex is absent from the unified link inventory")
    if dispatch["cases"] != 708 or dispatch["passed"] != 708:
        raise RuntimeError("Flex is absent from the global dispatcher gate")

    evidence = {
        "schema": 1,
        "release": "2.6.4",
        "recorded_at": "2026-11-23",
        "status": "complete translated multicall integration",
        "public_names": ["flex", "flex++", "lex"],
        "translated_entrypoint": "rustbox_flex_main",
        "native_frontend_entrypoints": ["rustbox_flexpp_main", "rustbox_lex_main"],
        "namespaced_symbols": len(link["flex_namespaced_symbols"]),
        "upstream_suite": {**counts, "log_sha256": sha256(upstream_path)},
        "differential": differential,
        "differential_sha256": sha256(differential_path),
        "frontends": frontends,
        "frontends_sha256": sha256(frontends_path),
        "valgrind": valgrind,
        "global_dispatch": {
            "total_public_names": link["total_dispatch_names"],
            "cases": dispatch["cases"],
            "passed": dispatch["passed"],
            "link_report_sha256": sha256(link_path),
            "dispatch_report_sha256": sha256(dispatch_path),
        },
    }
    output = ROOT / "evidence/flex-2.6.4-multicall.json"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "differential": differential["passed"], "frontends": frontends["passed"],
        "public_names": len(evidence["public_names"]), "upstream_tests": counts["pass"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
