#!/usr/bin/env python3
"""Independent exact comparisons between GCC and Clang Kmod 34.3 oracles."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path


PROGRAMS = ("kmod", "depmod", "insmod", "lsmod", "modinfo", "modprobe", "rmmod")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(binary: Path, name: str, arguments: list[str]) -> dict[str, object]:
    environment = dict(os.environ)
    environment.update({"LC_ALL": "C", "LANG": "C"})
    process = subprocess.run(
        [name, *arguments], executable=str(binary), env=environment,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=15,
    )
    return {
        "status": process.returncode,
        "stdout_sha256": digest(process.stdout),
        "stderr_sha256": digest(process.stderr),
        "stdout_bytes": len(process.stdout),
        "stderr_bytes": len(process.stderr),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gcc-root", required=True, type=Path)
    parser.add_argument("--clang-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    cases: list[tuple[str, list[str]]] = []
    for name in PROGRAMS:
        cases.extend((name, option) for option in (["--help"], ["--version"],
                                                    ["--definitely-invalid"]))
    cases.append(("lsmod", []))
    fixture = args.gcc_root / "testsuite/rootfs/test-modinfo/mod-simple.ko"
    cases.extend((
        ("modinfo", [str(fixture)]),
        ("modinfo", ["--field=license", str(fixture)]),
        ("modprobe", [
            "--dirname", str(args.gcc_root / "testsuite/rootfs/test-modprobe/show-depends"),
            "--set-version", "4.4.4", "--show-depends", "mod-simple",
        ]),
    ))

    records = []
    for name, arguments in cases:
        left = run(args.gcc_root / name, name, arguments)
        right = run(args.clang_root / name, name, arguments)
        passed = left == right
        records.append({
            "applet": name,
            "arguments": arguments,
            "gcc": left,
            "clang": right,
            "passed": passed,
        })
        if not passed:
            raise RuntimeError(
                f"{name} {arguments!r} differs: gcc={left!r} clang={right!r}"
            )

    evidence = {
        "schema": 1,
        "applets": len(PROGRAMS),
        "cases": len(records),
        "passed": sum(record["passed"] for record in records),
        "records": records,
    }
    if evidence["cases"] != 25:
        raise RuntimeError(f"expected 25 Kmod oracle cases, found {evidence['cases']}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: evidence[key] for key in ("applets", "cases", "passed")},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
