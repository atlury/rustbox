#!/usr/bin/env python3
"""Exact canonical comparisons for the remaining Inetutils clients."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path


DEFAULT = [
    ([], b""), (["--help"], b""), (["--usage"], b""),
    (["--version"], b""), (["--definitely-invalid"], b""),
]
PROGRAMS = {
    "rcp": ("src/rcp", DEFAULT),
    "rlogin": ("src/rlogin", DEFAULT),
    "rsh": ("src/rsh", DEFAULT),
    "ftp": ("ftp/ftp", DEFAULT + [
        (["--no-login"], b""),
        ([], b"help\nstatus\nquit\n"),
    ]),
    "talk": ("talk/talk", DEFAULT),
    "telnet": ("telnet/telnet", DEFAULT + [
        ([], b"help\nstatus\nquit\n"),
    ]),
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(binary: Path, arguments: list[str], stdin: bytes) -> dict[str, object]:
    environment = dict(os.environ)
    environment.update({"LC_ALL": "C", "LANG": "C", "TERM": "dumb"})
    try:
        process = subprocess.run(
            [binary.name, *arguments],
            executable=str(binary),
            env=environment,
            input=stdin,
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
        for arguments, stdin in cases:
            left = run(canonical, arguments, stdin)
            right = run(hybrid, arguments, stdin)
            passed = left == right and not left.get("timeout")
            records.append({
                "applet": name,
                "arguments": arguments,
                "stdin_sha256": digest(stdin),
                "stdin_bytes": len(stdin),
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
