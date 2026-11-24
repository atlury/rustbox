#!/usr/bin/env python3
"""Independent public-surface comparison for canonical IPRoute2 builds."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path


PROGRAMS = (
    "arpd", "bridge", "ctstat", "dcb", "devlink", "dpll", "genl",
    "ifstat", "ip", "lnstat", "netshaper", "nstat", "rdma", "routel",
    "rtacct", "rtmon", "rtstat", "ss", "tc", "tipc", "vdpa",
)
OPTIONS = ("-V", "-h", "--help")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def invoke(binary: Path, name: str, option: str) -> dict[str, object]:
    environment = dict(os.environ)
    environment.update({"LC_ALL": "C", "LANG": "C", "TZ": "UTC"})
    process = subprocess.run(
        [name, option],
        executable=str(binary),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        timeout=5,
        check=False,
    )
    # Script interpreters set sys.argv[0] to the physical script path even
    # when executable= supplies a stable logical argv[0].  Canonicalize only
    # that known path so the two independently built routel copies compare.
    stdout = process.stdout.replace(str(binary).encode(), name.encode())
    stderr = process.stderr.replace(str(binary).encode(), name.encode())
    return {
        "status": process.returncode,
        "stdout_bytes": len(stdout),
        "stdout_sha256": digest(stdout),
        "stderr_bytes": len(stderr),
        "stderr_sha256": digest(stderr),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gcc-root", required=True, type=Path)
    parser.add_argument("--clang-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    records = []
    passed = 0
    for name in PROGRAMS:
        for option in OPTIONS:
            gcc = invoke(args.gcc_root / name, name, option)
            clang = invoke(args.clang_root / name, name, option)
            exact = gcc == clang
            passed += int(exact)
            records.append({
                "name": f"{name}-{option}",
                "program": name,
                "arguments": [option],
                "gcc": gcc,
                "clang": clang,
                "passed": exact,
            })
    result = {
        "schema": 1,
        "programs": len(PROGRAMS),
        "cases": len(records),
        "passed": passed,
        "physical_argv0_normalized": True,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: result[key] for key in ("programs", "cases", "passed")}, sort_keys=True))
    return 0 if passed == len(records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
