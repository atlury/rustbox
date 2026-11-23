#!/usr/bin/env python3
"""Replay every proven Inetutils case through the unified Rustbox dispatcher."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import runpy
import subprocess
from pathlib import Path


SLICES = (
    ("inetutils-small-hybrid-differential.py", "plain"),
    ("inetutils-clients-02-differential.py", "plain"),
    ("inetutils-clients-03-differential.py", "stdin"),
    ("inetutils-daemons-04-differential.py", "daemon"),
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(binary: Path, argv: list[str], stdin: bytes | None) -> dict[str, object]:
    environment = dict(os.environ)
    environment.update({"LC_ALL": "C", "LANG": "C", "TERM": "dumb"})
    try:
        process = subprocess.run(
            argv,
            executable=str(binary),
            env=environment,
            input=stdin,
            stdin=subprocess.DEVNULL if stdin is None else None,
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
    parser.add_argument("--rustbox", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    records: list[dict[str, object]] = []
    programs: set[str] = set()
    test_root = Path(__file__).resolve().parent
    for filename, shape in SLICES:
        namespace = runpy.run_path(str(test_root / filename))
        if shape == "daemon":
            entries = ((name, relative, namespace["CASES"])
                       for name, relative in namespace["PROGRAMS"].items())
        else:
            entries = ((name, relative, cases)
                       for name, (relative, cases) in namespace["PROGRAMS"].items())
        for name, relative, cases in entries:
            programs.add(name)
            canonical = args.canonical_root / relative
            if not canonical.is_file():
                raise RuntimeError(f"missing canonical Inetutils binary: {canonical}")
            dispatch_name = f"inetutils-{name}" if name in {"hostname", "logger"} else name
            for case in cases:
                if shape == "stdin":
                    arguments, stdin = case
                else:
                    arguments, stdin = case, None
                left = run(canonical, [name, *arguments], stdin)
                right = run(args.rustbox, [args.rustbox.name, dispatch_name, *arguments], stdin)
                passed = left == right and not left.get("timeout")
                record = {
                    "applet": name,
                    "dispatch_name": dispatch_name,
                    "arguments": arguments,
                    "stdin_sha256": digest(stdin or b""),
                    "stdin_bytes": len(stdin or b""),
                    "canonical": left,
                    "multicall": right,
                    "passed": passed,
                }
                records.append(record)
                if not passed:
                    raise RuntimeError(
                        f"{name} {arguments!r} differs: canonical={left!r} multicall={right!r}"
                    )

    evidence = {
        "schema": 1,
        "applets": len(programs),
        "cases": len(records),
        "passed": sum(record["passed"] for record in records),
        "dispatch_aliases": {
            "hostname": "inetutils-hostname",
            "logger": "inetutils-logger",
        },
        "records": records,
    }
    if evidence["applets"] != 26 or evidence["cases"] != 133:
        raise RuntimeError(f"unexpected Inetutils coverage: {evidence['applets']}/26, {evidence['cases']}/133")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: evidence[key] for key in ("applets", "cases", "passed")},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
