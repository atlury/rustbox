#!/usr/bin/env python3
"""Exact canonical comparisons for the second Inetutils hybrid slice."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path


PROGRAMS = {
    "rexec": ("src/rexec", [
        [], ["--help"], ["--usage"], ["--version"],
        ["--definitely-invalid"], ["--port=bogus", "echo"],
    ]),
    "tftp": ("src/tftp", [
        [], ["--help"], ["--usage"], ["--version"],
        ["--definitely-invalid"], ["localhost", "bogus"],
    ]),
    "traceroute": ("src/traceroute", [
        [], ["--help"], ["--usage"], ["--version"],
        ["--definitely-invalid"], ["--max-hop=bogus", "localhost"],
        ["--type=bogus", "localhost"],
    ]),
    "ifconfig": ("ifconfig/ifconfig", [
        ["--help"], ["--usage"], ["--version"], ["--definitely-invalid"],
        ["rustbox-no-such-interface"],
    ]),
    "ping": ("ping/ping", [
        [], ["--help"], ["--usage"], ["--version"],
        ["--definitely-invalid"], ["--count=bogus", "localhost"],
        ["--type=bogus", "localhost"],
    ]),
    "ping6": ("ping/ping6", [
        [], ["--help"], ["--usage"], ["--version"],
        ["--definitely-invalid"], ["--count=bogus", "localhost"],
        ["--ttl=bogus", "localhost"],
    ]),
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(binary: Path, arguments: list[str]) -> dict[str, object]:
    environment = dict(os.environ)
    environment.update({"LC_ALL": "C", "LANG": "C", "TERM": "dumb"})
    try:
        process = subprocess.run(
            [binary.name, *arguments],
            executable=str(binary),
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        )
        return {
            "status": process.returncode,
            "stdout_sha256": digest(process.stdout),
            "stderr_sha256": digest(process.stderr),
            "stdout_bytes": len(process.stdout),
            "stderr_bytes": len(process.stderr),
        }
    except subprocess.TimeoutExpired as error:
        return {
            "timeout": True,
            "stdout_sha256": digest(error.stdout or b""),
            "stderr_sha256": digest(error.stderr or b""),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-root", required=True, type=Path)
    parser.add_argument("--hybrid-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    records = []
    for name, (relative, cases) in PROGRAMS.items():
        canonical = args.canonical_root / relative
        hybrid = args.hybrid_root / name
        if not canonical.is_file() or not hybrid.is_file():
            raise RuntimeError(f"missing Inetutils {name} differential input")
        for arguments in cases:
            left = run(canonical, arguments)
            right = run(hybrid, arguments)
            passed = left == right and not left.get("timeout")
            records.append({
                "applet": name,
                "arguments": arguments,
                "canonical": left,
                "hybrid": right,
                "passed": passed,
            })
            if not passed:
                raise RuntimeError(
                    f"{name} {arguments!r} differs: canonical={left!r} hybrid={right!r}"
                )

    evidence = {
        "schema": 1,
        "applets": len(PROGRAMS),
        "cases": len(records),
        "passed": sum(record["passed"] for record in records),
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "applets": len(PROGRAMS),
        "cases": len(records),
        "passed": evidence["passed"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
