#!/usr/bin/env python3
"""Compare Rustbox egrep/fgrep dispatch with canonical GNU wrappers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


def run(argv: list[str], directory: Path, environment: dict[str, str]) -> dict[str, object]:
    process = subprocess.run(
        argv,
        cwd=directory,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return {
        "status": process.returncode,
        "stdout_bytes": len(process.stdout),
        "stdout_sha256": hashlib.sha256(process.stdout).hexdigest(),
        "stderr_bytes": len(process.stderr),
        "stderr_sha256": hashlib.sha256(process.stderr).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-directory", type=Path, required=True)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--rustbox", type=Path)
    target.add_argument("--applet-directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    canonical = args.canonical_directory.resolve()
    rustbox = args.rustbox.resolve() if args.rustbox else None
    cases = (
        ("egrep-match", "egrep", "alpha|beta"),
        ("egrep-no-match", "egrep", "absent|missing"),
        ("fgrep-match", "fgrep", "a*b"),
        ("fgrep-no-match", "fgrep", "absent"),
    )
    records = []
    with tempfile.TemporaryDirectory(prefix="rustbox-grep-alias-") as temporary:
        directory = Path(temporary)
        (directory / "input").write_bytes(b"alpha\nbeta\na*b\n")
        environment = dict(os.environ)
        environment.update({
            "LC_ALL": "C",
            "TZ": "UTC",
            "POSIXLY_CORRECT": "1",
            "PATH": f"{canonical}:/usr/bin:/bin",
        })
        for name, alias, pattern in cases:
            oracle = run([str(canonical / alias), pattern, "input"], directory, environment)
            applet = [str(rustbox), alias] if rustbox else [str(args.applet_directory.resolve() / alias)]
            actual = run([*applet, pattern, "input"], directory, environment)
            if oracle != actual:
                raise RuntimeError(f"GNU {alias} multicall mismatch: {name}\n{oracle}\n{actual}")
            records.append({"name": name, "alias": alias, "exact": True, "result": oracle})
    report = {
        "schema": 1,
        "comparisons": len(records),
        "canonical_multicall_exact": True,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"comparisons": len(records), "exact": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
