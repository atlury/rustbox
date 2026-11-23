#!/usr/bin/env python3
"""Independent exact comparisons between GCC and Clang Kmod 34.3 oracles."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path


PROGRAMS = ("kmod", "depmod", "insmod", "lsmod", "modinfo", "modprobe", "rmmod")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_live_lsmod(data: bytes) -> bytes:
    """Mask only the kernel-maintained live reference count column."""
    lines = data.splitlines(keepends=True)
    if not lines or lines[0] != b"Module                  Size  Used by\n":
        raise RuntimeError("unexpected lsmod heading")
    normalized = [lines[0]]
    pattern = re.compile(rb"^(\S+\s+\d+\s+)\d+(\s.*)?(\n?)$")
    for line in lines[1:]:
        match = pattern.match(line)
        if match is None:
            raise RuntimeError(f"unexpected lsmod row: {line!r}")
        normalized.append(match.group(1) + b"<live>" + (match.group(2) or b"") + match.group(3))
    return b"".join(normalized)


def run(binary: Path, name: str, arguments: list[str]) -> dict[str, object]:
    environment = dict(os.environ)
    environment.update({"LC_ALL": "C", "LANG": "C"})
    process = subprocess.run(
        [name, *arguments], executable=str(binary), env=environment,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=15,
    )
    stdout = process.stdout
    normalization = None
    if name == "lsmod" and not arguments:
        stdout = normalize_live_lsmod(stdout)
        normalization = "mask kernel-maintained Used-by reference count only"
    result = {
        "status": process.returncode,
        "stdout_sha256": digest(stdout),
        "stderr_sha256": digest(process.stderr),
        "stdout_bytes": len(stdout),
        "stderr_bytes": len(process.stderr),
    }
    if normalization:
        result["stdout_normalization"] = normalization
    return result


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
