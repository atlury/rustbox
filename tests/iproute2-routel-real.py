#!/usr/bin/env python3
"""Compare canonical routel with the native frontend using real route tables."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def invoke(command: list[str], environment: dict[str, str]) -> tuple[int, bytes, bytes]:
    process = subprocess.run(
        command,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    return process.returncode, process.stdout, process.stderr


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", required=True, type=Path)
    parser.add_argument("--canonical-ip-directory", required=True, type=Path)
    parser.add_argument("--native", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    environment = os.environ.copy()
    environment.update(
        {
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": f"{args.canonical_ip_directory}:{environment.get('PATH', '')}",
        }
    )
    cases = [
        ("default", []),
        ("ipv4-default", ["-4"]),
        ("ipv4-all", ["-4", "all"]),
        ("ipv4-main", ["--family=inet", "main"]),
        ("ipv6-default", ["-6"]),
        ("ipv6-all", ["-6", "all"]),
    ]
    records = []
    for name, arguments in cases:
        canonical = invoke(
            [sys.executable, str(args.canonical), *arguments], environment
        )
        native = invoke([str(args.native), *arguments], environment)
        if canonical != native:
            raise RuntimeError(
                f"real routel mismatch for {name}: canonical={canonical!r} "
                f"native={native!r}"
            )
        records.append(
            {
                "name": name,
                "arguments": arguments,
                "passed": True,
                "status": canonical[0],
                "stdout_bytes": len(canonical[1]),
                "stdout_sha256": sha256(canonical[1]),
                "stderr_bytes": len(canonical[2]),
                "stderr_sha256": sha256(canonical[2]),
            }
        )

    result = {
        "schema": 1,
        "release": "7.3.0",
        "cases": len(records),
        "passed": len(records),
        "real_kernel_routes": True,
        "canonical_native_exact": True,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"cases": len(records), "passed": len(records)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
