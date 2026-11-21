#!/usr/bin/env python3
"""Differential contracts for all canonical XZ Utils 5.8.4 public names."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


NAMES = [
    "xz", "unxz", "xzcat", "lzma", "unlzma", "lzcat", "xzdec",
    "lzmadec", "lzmainfo", "xzdiff", "xzcmp", "xzegrep", "xzfgrep",
    "xzgrep", "xzless", "xzmore", "lzdiff", "lzcmp", "lzgrep",
    "lzegrep", "lzfgrep", "lzmore", "lzless",
]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(directory: Path, name: str, arguments: list[str], stdin: bytes = b"") -> dict[str, object]:
    environment = os.environ.copy()
    environment.update({
        "LC_ALL": "C", "LANG": "C", "PAGER": "cat", "LESS": "-F -X",
        "PATH": str(directory) + os.pathsep + environment["PATH"],
    })
    result = subprocess.run(
        [f"./{name}", *arguments], input=stdin, cwd=directory,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment,
    )
    return {
        "status": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def serial(value: dict[str, object]) -> dict[str, object]:
    return {
        "status": value["status"],
        "stdout_sha256": digest(value["stdout"]),
        "stderr_sha256": digest(value["stderr"]),
        "stdout_bytes": len(value["stdout"]),
        "stderr_bytes": len(value["stderr"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gcc-directory", type=Path, required=True)
    parser.add_argument("--clang-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases: list[dict[str, object]] = []

    def compare(label: str, name: str, arguments: list[str], stdin: bytes = b"") -> None:
        left = run(args.gcc_directory, name, arguments, stdin)
        right = run(args.clang_directory, name, arguments, stdin)
        passed = left == right
        cases.append({"label": label, "name": name, "arguments": arguments,
                      "passed": passed, "gcc": serial(left), "clang": serial(right)})
        if not passed:
            raise RuntimeError(f"XZ compiler differential mismatch: {label}")

    for name in NAMES:
        compare(f"{name}-help", name, ["--help"])
        compare(f"{name}-version", name, ["--version"])

    payload = (b"alpha beta gamma\nneedle one\n" * 257) + bytes(range(256))
    with tempfile.TemporaryDirectory(prefix="rustbox-xz-differential-") as temporary:
        root = Path(temporary)
        plain = root / "input.txt"
        plain.write_bytes(payload)
        for directory, suffix in ((args.gcc_directory, "gcc"), (args.clang_directory, "clang")):
            result = run(directory, "xz", ["--stdout", "--check=sha256", str(plain)])
            if result["status"] != 0:
                raise RuntimeError(f"XZ {suffix} fixture compression failed")
            (root / f"input-{suffix}.xz").write_bytes(result["stdout"])
            result = run(directory, "lzma", ["--stdout", str(plain)])
            if result["status"] != 0:
                raise RuntimeError(f"LZMA {suffix} fixture compression failed")
            (root / f"input-{suffix}.lzma").write_bytes(result["stdout"])

        if (root / "input-gcc.xz").read_bytes() != (root / "input-clang.xz").read_bytes():
            raise RuntimeError("XZ compiler builds emitted different .xz streams")
        if (root / "input-gcc.lzma").read_bytes() != (root / "input-clang.lzma").read_bytes():
            raise RuntimeError("XZ compiler builds emitted different .lzma streams")

        xz_file = root / "input-gcc.xz"
        lzma_file = root / "input-gcc.lzma"
        compare("xz-stdin-roundtrip", "xz", ["--decompress", "--stdout"], xz_file.read_bytes())
        compare("unxz-file", "unxz", ["--stdout", str(xz_file)])
        compare("xzcat-file", "xzcat", [str(xz_file)])
        compare("xz-test", "xz", ["--test", str(xz_file)])
        compare("xz-list", "xz", ["--list", "--verbose", str(xz_file)])
        compare("unlzma-file", "unlzma", ["--stdout", str(lzma_file)])
        compare("lzcat-file", "lzcat", [str(lzma_file)])
        compare("xzdec-file", "xzdec", [str(xz_file)])
        compare("lzmadec-file", "lzmadec", [str(lzma_file)])
        compare("lzmainfo-file", "lzmainfo", [str(lzma_file)])
        for name in ("xzgrep", "xzegrep", "xzfgrep"):
            compare(f"{name}-match", name, ["needle", str(xz_file)])
        for name in ("lzgrep", "lzegrep", "lzfgrep"):
            compare(f"{name}-match", name, ["needle", str(lzma_file)])
        for name in ("xzdiff", "xzcmp"):
            compare(f"{name}-equal", name, [str(xz_file), str(plain)])
        for name in ("lzdiff", "lzcmp"):
            compare(f"{name}-equal", name, [str(lzma_file), str(plain)])
        for name in ("xzless", "xzmore"):
            compare(f"{name}-view", name, [str(xz_file)])
        for name in ("lzless", "lzmore"):
            compare(f"{name}-view", name, [str(lzma_file)])

    output = {
        "schema": 1, "release": "5.8.4", "public_names": NAMES,
        "cases": len(cases), "passed": sum(case["passed"] for case in cases),
        "results": cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"cases": output["cases"], "passed": output["passed"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
