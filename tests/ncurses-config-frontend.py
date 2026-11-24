#!/usr/bin/env python3
"""Exact differential for the native ncursesw6-config frontend."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path


OPTIONS = [
    "--prefix",
    "--exec-prefix",
    "--cflags",
    "--cflags-only-I",
    "--cflags-only-other",
    "--libs",
    "--libs-only-L",
    "--libs-only-l",
    "--libs-only-other",
    "--version",
    "--abi-version",
    "--mouse-version",
    "--bindir",
    "--datadir",
    "--includedir",
    "--libdir",
    "--mandir",
    "--terminfo",
    "--terminfo-dirs",
    "--termpath",
    "--help",
]


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def run(binary: Path, arguments: list[str]) -> tuple[int, bytes, bytes]:
    environment = os.environ.copy()
    environment.update(
        {"LANG": "C", "LANGUAGE": "C", "LC_ALL": "C", "LC_CTYPE": "C"}
    )
    process = subprocess.run(
        ["ncursesw6-config", *arguments],
        executable=binary,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
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
    parser.add_argument("--canonical", required=True, type=Path)
    parser.add_argument("--native", required=True, type=Path, action="append")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    cases: list[tuple[str, list[str]]] = [("no-option", [])]
    cases.extend((option[2:], [option]) for option in OPTIONS)
    cases.extend(
        [
            ("all-queries", OPTIONS[:-1]),
            ("reverse-queries", list(reversed(OPTIONS[:-1]))),
            ("repeat", ["--version", "--version", "--libs", "--libs"]),
            ("help-then-query", ["--help", "--version"]),
            ("query-then-help", ["--version", "--help"]),
            ("unknown", ["--definitely-invalid"]),
            ("empty-option", [""]),
            ("query-then-unknown", ["--version", "--definitely-invalid"]),
            ("help-then-unknown", ["--help", "--definitely-invalid"]),
        ]
    )

    records: list[dict[str, object]] = []
    for name, arguments in cases:
        canonical = run(args.canonical.resolve(), arguments)
        native_results = [run(path.resolve(), arguments) for path in args.native]
        passed = all(result == canonical for result in native_results)
        records.append(
            {
                "name": name,
                "arguments": arguments,
                "passed": passed,
                "result": summarized(canonical),
            }
        )
        if not passed:
            raise RuntimeError(
                f"ncursesw6-config mismatch for {name}: "
                f"canonical={canonical!r}, native={native_results!r}"
            )

    evidence = {
        "schema": 1,
        "release": "6.6",
        "configured_version": "6.6.20251230",
        "cases": len(records),
        "passed": len(records),
        "native_frontends": len(args.native),
        "canonical_native_exact": True,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"cases": len(records), "passed": len(records)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
