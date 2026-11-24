#!/usr/bin/env python3
"""Exact public-surface comparison for translated IPRoute2 program closures."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path


PROGRAMS = (
    "arpd", "bridge", "dcb", "devlink", "dpll", "genl", "ifstat", "ip",
    "lnstat", "netshaper", "nstat", "rdma", "rtacct", "rtmon", "ss", "tc",
    "tipc", "vdpa",
)
OPTIONS = ("-V", "-h", "--help")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def invoke(binary: Path, name: str, arguments: list[str]) -> tuple[int, bytes, bytes]:
    environment = os.environ.copy()
    environment.update({"LANG": "C", "LC_ALL": "C", "TZ": "UTC"})
    process = subprocess.run(
        [name, *arguments],
        executable=binary,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=5,
        check=False,
    )
    return process.returncode, process.stdout, process.stderr


def summarized(result: tuple[int, bytes, bytes]) -> dict[str, object]:
    status, stdout, stderr = result
    return {
        "status": status,
        "stdout_bytes": len(stdout),
        "stdout_sha256": sha256(stdout),
        "stderr_bytes": len(stderr),
        "stderr_sha256": sha256(stderr),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-root", required=True, type=Path)
    parser.add_argument("--hybrid-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    records = []
    for program in PROGRAMS:
        for option in OPTIONS:
            canonical = invoke(args.canonical_root / program, program, [option])
            hybrid = invoke(args.hybrid_root / program, program, [option])
            passed = canonical == hybrid
            records.append({
                "program": program,
                "arguments": [option],
                "passed": passed,
                "canonical": summarized(canonical),
                "hybrid": summarized(hybrid),
            })
            if not passed:
                raise RuntimeError(
                    f"IPRoute2 hybrid mismatch: {program} {option}: "
                    f"canonical={canonical!r} hybrid={hybrid!r}"
                )

    result = {
        "schema": 1,
        "release": "7.3.0",
        "programs": len(PROGRAMS),
        "cases": len(records),
        "passed": len(records),
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: result[key] for key in ("programs", "cases", "passed")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
