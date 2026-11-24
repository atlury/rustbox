#!/usr/bin/env python3
"""Exact public-surface comparison for IPRoute2 inside global Rustbox."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


ENGINES = (
    "arpd", "bridge", "dcb", "devlink", "dpll", "genl", "ifstat", "ip",
    "lnstat", "netshaper", "nstat", "rdma", "rtacct", "rtmon", "ss", "tc",
    "tipc", "vdpa",
)
ALIASES = {"ctstat": "lnstat", "rtstat": "lnstat"}
OPTIONS = ("-V", "-h", "--help")
ROUTEL_CASES = (
    ("default", ()),
    ("ipv4-default", ("-4",)),
    ("ipv4-all", ("-4", "all")),
    ("ipv4-main", ("--family=inet", "main")),
    ("ipv6-default", ("-6",)),
    ("ipv6-all", ("-6", "all")),
)


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def invoke(
    command: list[str], environment: dict[str, str], executable: Path | None = None
) -> tuple[int, bytes, bytes]:
    process = subprocess.run(
        command,
        executable=executable,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
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
    parser.add_argument("--canonical-routel", required=True, type=Path)
    parser.add_argument("--rustbox", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    environment = os.environ.copy()
    environment.update(
        {
            "LANG": "C",
            "LC_ALL": "C",
            "TZ": "UTC",
            "PATH": f"{args.canonical_root}:{environment.get('PATH', '')}",
        }
    )
    records: list[dict[str, object]] = []
    public_engines = (*ENGINES, *ALIASES)
    for name in public_engines:
        target = ALIASES.get(name, name)
        canonical_binary = args.canonical_root / target
        for option in OPTIONS:
            canonical = invoke(
                [name, option], environment, executable=canonical_binary
            )
            multicall = invoke(
                [str(args.rustbox), name, option], environment
            )
            passed = canonical == multicall
            records.append(
                {
                    "program": name,
                    "engine": target,
                    "arguments": [option],
                    "passed": passed,
                    "canonical": summarized(canonical),
                    "multicall": summarized(multicall),
                }
            )
            if not passed:
                raise RuntimeError(
                    f"IPRoute2 multicall mismatch: {name} {option}: "
                    f"canonical={canonical!r} multicall={multicall!r}"
                )

    routel_environment = dict(environment)
    routel_environment.update({"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"})
    for case_name, arguments in ROUTEL_CASES:
        canonical = invoke(
            [sys.executable, str(args.canonical_routel), *arguments],
            routel_environment,
        )
        multicall = invoke(
            [str(args.rustbox), "routel", *arguments], routel_environment
        )
        passed = canonical == multicall
        records.append(
            {
                "program": "routel",
                "name": case_name,
                "arguments": list(arguments),
                "passed": passed,
                "canonical": summarized(canonical),
                "multicall": summarized(multicall),
            }
        )
        if not passed:
            raise RuntimeError(
                f"IPRoute2 multicall mismatch: routel {case_name}: "
                f"canonical={canonical!r} multicall={multicall!r}"
            )

    public_names = (*public_engines, "routel")
    result = {
        "schema": 1,
        "release": "7.3.0",
        "public_names": list(public_names),
        "public_name_count": len(public_names),
        "translated_engines": len(ENGINES),
        "aliases": ALIASES,
        "cases": len(records),
        "passed": len(records),
        "canonical_multicall_exact": True,
        "real_kernel_routel_cases": len(ROUTEL_CASES),
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                key: result[key]
                for key in ("public_name_count", "cases", "passed")
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
