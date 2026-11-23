#!/usr/bin/env python3
"""Compare the native curl-config frontend with canonical generated policy."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(binary: Path, arguments: list[str]) -> dict[str, object]:
    process = subprocess.run(
        [str(binary), *arguments], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    return {
        "status": process.returncode,
        "stdout_sha256": sha256(process.stdout),
        "stderr_sha256": sha256(process.stderr),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", required=True, type=Path)
    parser.add_argument("--native", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    cases = [
        ("no-option", []),
        ("help", ["--help"]),
        ("built-shared", ["--built-shared"]),
        ("ca", ["--ca"]),
        ("cc", ["--cc"]),
        ("cflags", ["--cflags"]),
        ("configure", ["--configure"]),
        ("feature", ["--feature"]),
        ("features", ["--features"]),
        ("libs", ["--libs"]),
        ("prefix", ["--prefix"]),
        ("protocols", ["--protocols"]),
        ("ssl-backends", ["--ssl-backends"]),
        ("static-libs", ["--static-libs"]),
        ("version", ["--version"]),
        ("vernum", ["--vernum"]),
        ("check-equal", ["--checkfor", "8.23.0"]),
        ("check-older", ["--checkfor", "7.99.99"]),
        ("check-patch-suffix", ["--checkfor", "8.23.0-pre1"]),
        ("check-newer-patch", ["--checkfor", "8.23.1"]),
        ("check-newer-major", ["--checkfor", "9.0.0"]),
        ("multiple", ["--built-shared", "--ca", "--prefix", "--libs"]),
        ("early-version", ["--built-shared", "--version", "--protocols"]),
        ("unknown", ["--definitely-invalid"]),
    ]
    records = []
    for name, arguments in cases:
        # Preserve argv[0] when the native frontend is a multicall symlink.
        canonical = run(args.canonical.absolute(), arguments)
        native = run(args.native.absolute(), arguments)
        passed = canonical == native
        records.append({
            "name": name,
            "arguments": arguments,
            "passed": passed,
            "result": canonical,
        })
        if not passed:
            raise RuntimeError(
                f"curl-config mismatch for {name}: {canonical} != {native}"
            )
    evidence = {
        "schema": 1,
        "cases": len(records),
        "passed": len(records),
        "canonical_native_exact": True,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"cases": len(records), "passed": len(records)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
