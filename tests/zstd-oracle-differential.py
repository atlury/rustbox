#!/usr/bin/env python3
"""Compiler-independent contracts for all zstd 1.5.7 installed commands."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


NAMES = ["zstd", "zstdmt", "unzstd", "zstdcat", "zstdgrep", "zstdless"]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(directory: Path, name: str, arguments: list[str], stdin: bytes = b"") -> dict[str, object]:
    environment = os.environ.copy()
    environment.update({
        "LC_ALL": "C", "LANG": "C", "PAGER": "cat", "LESS": "-F -X",
        # Use the already-verified canonical Less oracle for both zstd builds.
        # zstdless is a shell adapter and upstream intentionally does not ship
        # its pager dependency.
        "PATH": str(directory) + os.pathsep + "/rustbox-less/oracle-gcc" +
        os.pathsep + environment["PATH"],
        "ZSTD": str(directory / "zstd"), "ZCAT": str(directory / "zstdcat"),
    })
    result = subprocess.run(
        [str(directory / name), *arguments], input=stdin,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment,
    )
    return {"status": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


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
        cases.append({
            "label": label, "name": name, "arguments": arguments,
            "passed": passed, "gcc": serial(left), "clang": serial(right),
        })
        if not passed:
            raise RuntimeError(f"zstd compiler differential mismatch: {label}")

    for name in ("zstd", "zstdmt", "unzstd", "zstdcat"):
        compare(f"{name}-help", name, ["--help"])
        compare(f"{name}-version", name, ["--version"])

    payload = (b"alpha beta gamma\nneedle one\n" * 1024) + bytes(range(256))
    with tempfile.TemporaryDirectory(prefix="rustbox-zstd-differential-") as temporary:
        root = Path(temporary)
        plain = root / "input.txt"
        plain.write_bytes(payload)
        streams: dict[str, bytes] = {}
        for directory, compiler in ((args.gcc_directory, "gcc"), (args.clang_directory, "clang")):
            compressed = run(directory, "zstd", ["-T1", "--stdout", str(plain)])
            if compressed["status"] != 0:
                raise RuntimeError(f"zstd {compiler} fixture compression failed")
            streams[compiler] = compressed["stdout"]
        if streams["gcc"] != streams["clang"]:
            raise RuntimeError("zstd compiler builds emitted different frames")
        frame = root / "input.zst"
        frame.write_bytes(streams["gcc"])

        compare("zstd-stdin-roundtrip", "zstd", ["--decompress", "--stdout"], streams["gcc"])
        compare("unzstd-file", "unzstd", ["--stdout", str(frame)])
        compare("zstdcat-file", "zstdcat", [str(frame)])
        compare("zstd-test", "zstd", ["--test", str(frame)])
        compare("zstd-list", "zstd", ["--list", str(frame)])
        compare("zstdmt-compress", "zstdmt", ["-T1", "--stdout", str(plain)])
        compare("zstdgrep-match", "zstdgrep", ["needle", str(frame)])
        compare("zstdgrep-no-match", "zstdgrep", ["absent-pattern", str(frame)])
        compare("zstdless-view", "zstdless", [str(frame)])

    output = {
        "schema": 1, "release": "1.5.7", "public_names": NAMES,
        "configuration": {"threads": True, "zlib": False, "lzma": False, "lz4": False},
        "cases": len(cases), "passed": sum(case["passed"] for case in cases),
        "results": cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"cases": output["cases"], "passed": output["passed"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
