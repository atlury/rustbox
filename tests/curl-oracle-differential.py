#!/usr/bin/env python3
"""Compare deterministic curl CLI and file-protocol behavior across compilers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tree(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): sha256(path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".home/" not in str(path.relative_to(root))
    }


def run(binary: Path, arguments: list[str], fixtures: dict[str, bytes]) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="rustbox-curl-diff-") as directory:
        root = Path(directory)
        for name, data in fixtures.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            os.utime(target, (1_600_000_000, 1_600_000_000))
        home = root / ".home"
        home.mkdir()
        expanded = [argument.replace("{root}", str(root)) for argument in arguments]
        environment = os.environ.copy()
        environment.update({"HOME": str(home), "LC_ALL": "C", "TZ": "UTC"})
        result = subprocess.run(
            [str(binary), "--disable", *expanded], cwd=root, env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        root_bytes = str(root).encode()
        stdout = result.stdout.replace(root_bytes, b"{root}")
        stderr = result.stderr.replace(root_bytes, b"{root}")
        return {
            "status": result.returncode,
            "stdout_sha256": sha256(stdout),
            "stderr_sha256": sha256(stderr),
            "tree": tree(root),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gcc", type=Path, required=True)
    parser.add_argument("--clang", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Preserve the final invoked path component: multicall frontends rely on
    # argv[0], and resolve() would dereference a curl symlink back to rustbox.
    gcc = args.gcc.absolute()
    clang = args.clang.absolute()
    payload = b"zero\none two\nthree-four-five\nlast\n"
    fixtures = {"payload.txt": payload, "second.txt": b"second payload\n"}
    cases = [
        ("version", ["--version"]),
        ("help", ["--help", "all"]),
        ("manual", ["--manual"]),
        ("invalid-option", ["--definitely-not-a-curl-option"]),
        ("missing-url", []),
        ("file-basic", ["--silent", "file://{root}/payload.txt"]),
        ("file-range", ["--silent", "--range", "5-18", "file://{root}/payload.txt"]),
        ("file-head", ["--silent", "--head", "file://{root}/payload.txt"]),
        ("file-writeout", [
            "--silent", "--write-out", "%{response_code}:%{size_download}:%{url_effective}\\n",
            "file://{root}/payload.txt",
        ]),
        ("file-output", [
            "--silent", "--output", "downloaded.txt", "file://{root}/payload.txt",
        ]),
        ("file-two-transfers", [
            "--silent", "file://{root}/payload.txt", "--next", "--silent",
            "file://{root}/second.txt",
        ]),
        ("unsupported-https", ["--silent", "--show-error", "https://127.0.0.1/"]),
    ]
    records = []
    for name, arguments in cases:
        gcc_result = run(gcc, arguments, fixtures)
        clang_result = run(clang, arguments, fixtures)
        passed = gcc_result == clang_result
        records.append({
            "name": name, "arguments": arguments, "passed": passed,
            "result": gcc_result,
        })
        if not passed:
            raise RuntimeError(f"curl GCC/Clang mismatch for {name}: {gcc_result} != {clang_result}")
    evidence = {
        "schema": 1, "cases": len(records), "passed": len(records),
        "gcc_clang_exact": True, "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"cases": len(records), "passed": len(records)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
