#!/usr/bin/env python3
"""Independent public-interface comparisons for canonical Procps-ng builds."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


PROGRAMS = (
    "free", "hugetop", "kill", "pgrep", "pidof", "pidwait", "pkill",
    "pmap", "ps", "pwdx", "skill", "slabtop", "snice", "sysctl",
    "tload", "top", "uptime", "vmstat", "w", "watch",
)


@dataclass(frozen=True)
class Case:
    program: str
    arguments: tuple[str, ...]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def invoke(root: Path, library: Path, case: Case) -> dict[str, object]:
    environment = os.environ.copy()
    environment.update({
        "LC_ALL": "C",
        "LANG": "C",
        "TZ": "UTC",
        "COLUMNS": "80",
        "LINES": "24",
        "LD_LIBRARY_PATH": str(library),
    })
    process = subprocess.run(
        [str(root / case.program), *case.arguments],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=15,
    )
    return {
        "status": process.returncode,
        "stdout_bytes": len(process.stdout),
        "stdout_sha256": digest(process.stdout),
        "stderr_bytes": len(process.stderr),
        "stderr_sha256": digest(process.stderr),
    }


def cases() -> list[Case]:
    public = [
        Case(program, (option,))
        for program in PROGRAMS
        for option in ("--help", "--version")
    ]
    deterministic = [
        Case("kill", ("-l", "TERM")),
        Case("kill", ("-l", "15")),
        Case("pgrep", ("[",)),
        Case("pidof", ("rustbox-procps-process-does-not-exist",)),
        Case("pidwait", ("rustbox-procps-process-does-not-exist",)),
        Case("pmap", ("999999999",)),
        Case("ps", ("-o", "pid=,comm=", "-p", "1")),
        Case("pwdx", ("999999999",)),
        Case("sysctl", ("-n", "kernel.ostype")),
        Case("sysctl", ("rustbox.procps.key.does.not.exist",)),
        Case("uptime", ("--since",)),
    ]
    return public + deterministic


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gcc-root", required=True, type=Path)
    parser.add_argument("--gcc-library", required=True, type=Path)
    parser.add_argument("--clang-root", required=True, type=Path)
    parser.add_argument("--clang-library", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    records = []
    for case in cases():
        gcc = invoke(args.gcc_root, args.gcc_library, case)
        clang = invoke(args.clang_root, args.clang_library, case)
        records.append({
            "program": case.program,
            "arguments": list(case.arguments),
            "gcc": gcc,
            "clang": clang,
            "passed": gcc == clang,
        })
    passed = sum(record["passed"] for record in records)
    result = {
        "schema": 1,
        "programs": len(PROGRAMS),
        "cases": len(records),
        "passed": passed,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: result[key] for key in ("programs", "cases", "passed")}, sort_keys=True))
    return 0 if passed == len(records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
