#!/usr/bin/env python3
"""Compare independent canonical builds of Less's complete command surface."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Case:
    name: str
    applet: str
    arguments: tuple[str, ...]
    stdin: bytes = b""
    files: tuple[tuple[str, bytes], ...] = ()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def invoke(directory: Path, case: Case) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="rustbox-less-oracle-") as temporary:
        root = Path(temporary)
        for name, content in case.files:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        environment = os.environ.copy()
        environment.update({
            "HOME": str(root),
            "LANG": "C",
            "LC_ALL": "C",
            "LESS": "",
            "LESSHISTFILE": "-",
            "TERM": "xterm",
            "TZ": "UTC",
        })
        process = subprocess.run(
            [str(directory / case.applet), *case.arguments],
            cwd=root,
            env=environment,
            input=case.stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
        )
        after = {
            name: digest((root / name).read_bytes())
            for name, _ in case.files
            if (root / name).is_file()
        }
        return {
            "status": process.returncode,
            "stdout_bytes": len(process.stdout),
            "stdout_sha256": digest(process.stdout),
            "stderr_bytes": len(process.stderr),
            "stderr_sha256": digest(process.stderr),
            "files": after,
        }


def cases() -> list[Case]:
    text = b"alpha\n\nbeta\nbeta\ngamma\n"
    long = (b"0123456789" * 20) + b"\nsecond\n"
    return [
        Case("less-version-short", "less", ("-V",)),
        Case("less-version-long", "less", ("--version",)),
        Case("less-help-short", "less", ("-?",)),
        Case("less-help-long", "less", ("--help",)),
        Case("less-invalid-option", "less", ("--definitely-invalid",)),
        Case("less-stdin", "less", (), stdin=text),
        Case("less-empty-stdin", "less", ()),
        Case("less-file", "less", ("input",), files=(("input", text),)),
        Case("less-multiple-files", "less", ("one", "two"), files=(("one", text), ("two", long))),
        Case("less-squeeze", "less", ("-s", "input"), files=(("input", text),)),
        Case("less-chop", "less", ("-S", "input"), files=(("input", long),)),
        Case("less-search", "less", ("-pbeta", "input"), files=(("input", text),)),
        Case("less-missing", "less", ("missing",)),
        Case("less-double-dash", "less", ("--", "-input"), files=(("-input", text),)),
        Case("lessecho-version", "lessecho", ("--version",)),
        Case("lessecho-help", "lessecho", ("--help",)),
        Case("lessecho-plain", "lessecho", ("alpha", "beta gamma")),
        Case("lessecho-quote-all", "lessecho", ("-a", "alpha", "beta gamma")),
        Case("lessecho-metachar", "lessecho", ("-m*", "alpha*beta", "plain")),
        Case("lessecho-no-escape", "lessecho", ("-m*", "-e-", "alpha*beta")),
        Case("lessecho-numeric-quotes", "lessecho", ("-p91", "-d93", "-a", "alpha")),
        Case("lessecho-invalid", "lessecho", ("--invalid",)),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gcc-directory", type=Path, required=True)
    parser.add_argument("--clang-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = []
    for case in cases():
        gcc = invoke(args.gcc_directory, case)
        clang = invoke(args.clang_directory, case)
        if gcc != clang:
            raise RuntimeError(f"Less/{case.name}: GCC {gcc} != Clang {clang}")
        records.append({"name": case.name, "applet": case.applet, "result": gcc})
    payload = {"schema": 1, "cases": len(records), "passed": len(records), "records": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Less canonical differential: {len(records)}/{len(records)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
