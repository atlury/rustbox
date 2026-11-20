#!/usr/bin/env python3
"""Generate committed evidence for the unified Rustbox multicall executable."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--link-report", type=Path, required=True)
    parser.add_argument("--dispatch-report", type=Path, required=True)
    parser.add_argument("--differential-report", type=Path, required=True)
    parser.add_argument("--m4-report-directory", type=Path, required=True)
    parser.add_argument("--pkgconf-report-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    binary = args.binary.resolve()
    link = json.loads(args.link_report.read_text(encoding="utf-8"))
    dispatch = json.loads(args.dispatch_report.read_text(encoding="utf-8"))
    differential = json.loads(args.differential_report.read_text(encoding="utf-8"))
    m4_directory = args.m4_report_directory.resolve()
    pkgconf_directory = args.pkgconf_report_directory.resolve()
    m4_differential = json.loads((m4_directory / "differential.json").read_text())
    m4_language = (m4_directory / "language-check.log").read_text(errors="replace")
    m4_valgrind = (m4_directory / "valgrind.log").read_text(errors="replace")
    if dispatch["cases"] != 534 or dispatch["passed"] != 534 or dispatch["failures"]:
        raise RuntimeError("unified dispatcher comparison is incomplete")
    if (
        differential["batches"] != 38
        or differential["cases"] != 14022
        or differential["passed"] != 14022
        or differential["failed_batches"]
    ):
        raise RuntimeError("unified batch differential comparison is incomplete")
    m4_numbered = set(re.findall(r"^Checking .*/checks/(\d{3})\.", m4_language, re.MULTILINE))
    if (
        len(m4_numbered) != 242
        or "All checks successful" not in m4_language
        or "stackovf.test" not in m4_language
        or not m4_differential["canonical_hybrid_exact"]
        or m4_differential["comparisons"] != 108
        or "ERROR SUMMARY: 0 errors" not in m4_valgrind
    ):
        raise RuntimeError("unified M4 integration comparison is incomplete")
    pkgconf_fixture_path = pkgconf_directory / "fixture-tests.log"
    pkgconf_fixture = pkgconf_fixture_path.read_text(errors="replace")
    pkgconf_fixture_passes = len(re.findall(r"^PASS:", pkgconf_fixture, re.MULTILINE))
    pkgconf_fixture_skips = len(re.findall(r"^SKIP:", pkgconf_fixture, re.MULTILINE))
    pkgconf_differential_path = pkgconf_directory / "differential.json"
    pkgconf_differential = json.loads(pkgconf_differential_path.read_text())
    pkgconf_valgrind_path = pkgconf_directory / "valgrind.log"
    pkgconf_valgrind = pkgconf_valgrind_path.read_text(errors="replace")
    if (
        pkgconf_fixture_passes != 429
        or pkgconf_fixture_skips != 5
        or re.search(r"^(?:FAIL|ERROR):", pkgconf_fixture, re.MULTILINE)
        or not pkgconf_differential["canonical_hybrid_exact"]
        or pkgconf_differential["comparisons"] != 55
        or "ERROR SUMMARY: 0 errors" not in pkgconf_valgrind
    ):
        raise RuntimeError("unified pkgconf integration comparison is incomplete")
    if sha256(binary) != link["binary"]["sha256"]:
        raise RuntimeError("unified binary changed after link evidence")
    with tempfile.TemporaryDirectory(prefix="rustbox-strip-") as temporary:
        stripped = Path(temporary) / "rustbox"
        shutil.copy2(binary, stripped)
        subprocess.run(["strip", "--strip-all", str(stripped)], check=True)
        stripped_bytes = stripped.stat().st_size
        stripped_sha256 = sha256(stripped)
    dynamic = subprocess.run(
        ["readelf", "-d", str(binary)], check=True, text=True, stdout=subprocess.PIPE
    ).stdout
    needed = sorted(set(re.findall(r"Shared library: \[([^]]+)\]", dynamic)))
    forbidden = [name for name in needed if "selinux" in name or "systemd" in name]
    undefined = subprocess.run(
        ["nm", "-u", str(binary)], check=True, text=True, stdout=subprocess.PIPE
    ).stdout
    forbidden_undefined = sorted(
        line.strip() for line in undefined.splitlines()
        if "selinux" in line.lower() or "systemd" in line.lower()
    )
    if forbidden or forbidden_undefined:
        raise RuntimeError("unified binary retains a forbidden SELinux/systemd dependency")
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-20",
        "status": "Coreutils, util-linux, GNU M4, and pkgconf integrated canonical parity",
        "scope": {
            "coreutils": 106,
            "util_linux": 155,
            "m4": 1,
            "pkgconf_public_names": 5,
            "dispatch_names": 267,
            "excluded": ["chcon", "runcon"],
        },
        "binary": {
            **link["binary"],
            "stripped_bytes": stripped_bytes,
            "stripped_sha256": stripped_sha256,
            "needed_libraries": needed,
            "selinux_dependencies": [],
            "systemd_dependencies": [],
        },
        "dispatch": dispatch,
        "batch_differential": differential,
        "m4_integration": {
            "numbered_language_checks": len(m4_numbered),
            "stack_overflow_check": "pass",
            "differential": m4_differential,
            "valgrind_errors": 0,
            "language_log_sha256": sha256(m4_directory / "language-check.log"),
            "valgrind_log_sha256": sha256(m4_directory / "valgrind.log"),
        },
        "pkgconf_integration": {
            "fixture_passes": pkgconf_fixture_passes,
            "intentional_platform_skips": pkgconf_fixture_skips,
            "differential": pkgconf_differential,
            "valgrind_errors": 0,
            "fixture_log_sha256": sha256(pkgconf_fixture_path),
            "valgrind_log_sha256": sha256(pkgconf_valgrind_path),
        },
        "collision_isolation": {
            "translated_libraries": len(link["source_library_sha256"]),
            "namespaced_libraries": len(link["namespaced_symbols"]),
            "namespaced_symbols": sum(len(items) for items in link["namespaced_symbols"].values()),
            "namespaced_support_objects": len(link["namespaced_support_symbols"]),
            "m4_namespaced_support_symbols": len(link["m4_namespaced_support_symbols"]),
            "manifest": link,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "dispatch": dispatch["passed"],
        "differential": differential["passed"],
        "stripped_bytes": stripped_bytes,
        "needed_libraries": len(needed),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
