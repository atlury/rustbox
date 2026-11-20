#!/usr/bin/env python3
"""Exact cross-compiler comparisons for the canonical File oracle."""

from __future__ import annotations

import argparse
import bz2
import gzip
import hashlib
import json
import lzma
import os
import socket
import subprocess
import tempfile
from pathlib import Path


def run(
    binary: Path,
    magic: Path,
    arguments: list[str],
    stdin: bytes | None = None,
) -> tuple[int, bytes, bytes]:
    environment = dict(os.environ)
    environment.update({"LC_ALL": "C", "TZ": "UTC"})
    result = subprocess.run(
        [str(binary), "-m", str(magic), *arguments],
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
    )
    return result.returncode, result.stdout, result.stderr


def digest(result: tuple[int, bytes, bytes]) -> str:
    status, stdout, stderr = result
    return hashlib.sha256(
        status.to_bytes(4, "little", signed=True) + stdout + b"\0" + stderr
    ).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gcc", type=Path, required=True)
    parser.add_argument("--clang", type=Path, required=True)
    parser.add_argument("--magic", type=Path, required=True)
    parser.add_argument("--upstream-tests", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    cases: list[tuple[str, list[str], bytes | None]] = []
    for fixture in sorted(args.upstream_tests.glob("*.testfile")):
        cases.append((f"upstream:{fixture.name}", [str(fixture)], None))

    with tempfile.TemporaryDirectory(prefix="rustbox-file-oracle-") as temporary:
        root = Path(temporary)
        payloads = {
            "empty": b"",
            "ascii": b"rustbox canonical file oracle\n",
            "utf8": "Rustbox λ 世界\n".encode(),
            "json": b'{"rustbox":true,"count":267}\n',
            "binary": bytes(range(256)),
            "png": b"\x89PNG\r\n\x1a\n" + b"\0" * 64,
        }
        paths: dict[str, Path] = {}
        for name, payload in payloads.items():
            path = root / name
            path.write_bytes(payload)
            paths[name] = path
        compressed = {
            "gzip": gzip.compress(payloads["ascii"]),
            "bzip2": bz2.compress(payloads["ascii"]),
            "xz": lzma.compress(payloads["ascii"]),
        }
        for name, payload in compressed.items():
            path = root / name
            path.write_bytes(payload)
            paths[name] = path

        flags = ([], ["-b"], ["-i"], ["-k"], ["--extension"], ["--apple"])
        for name, path in paths.items():
            for option in flags:
                cases.append((f"generated:{name}:{','.join(option) or 'default'}", [*option, str(path)], None))
        for name in compressed:
            cases.append((f"compressed:{name}:z", ["-z", str(paths[name])], None))
            cases.append((f"compressed:{name}:Z", ["-Z", str(paths[name])], None))

        directory = root / "directory"
        directory.mkdir()
        symlink = root / "symlink"
        symlink.symlink_to(paths["ascii"])
        broken = root / "broken"
        broken.symlink_to(root / "missing")
        fifo = root / "fifo"
        os.mkfifo(fifo)
        unix_socket = root / "socket"
        listener = socket.socket(socket.AF_UNIX)
        listener.bind(str(unix_socket))
        try:
            for name, path in (
                ("directory", directory),
                ("symlink", symlink),
                ("broken", broken),
                ("fifo", fifo),
                ("socket", unix_socket),
            ):
                cases.append((f"filesystem:{name}", [str(path)], None))
                cases.append((f"filesystem:{name}:brief", ["-b", str(path)], None))

            for name, payload in payloads.items():
                for option in ([], ["-b"], ["-i"]):
                    cases.append((f"stdin:{name}:{','.join(option) or 'default'}", [*option, "-"], payload))

            list_file = root / "inputs.list"
            list_file.write_text(f"{paths['ascii']}\n{paths['binary']}\n", encoding="utf-8")
            cases.extend(
                [
                    ("interface:help", ["--help"], None),
                    ("interface:version", ["--version"], None),
                    ("interface:list", ["-f", str(list_file)], None),
                ]
            )

            records = []
            for index, (name, arguments, stdin) in enumerate(cases):
                gcc = run(args.gcc, args.magic, arguments, stdin)
                clang = run(args.clang, args.magic, arguments, stdin)
                exact = gcc == clang
                records.append(
                    {
                        "index": index,
                        "name": name,
                        "arguments": arguments,
                        "gcc_sha256": digest(gcc),
                        "clang_sha256": digest(clang),
                        "exact": exact,
                    }
                )
                if not exact:
                    raise RuntimeError(f"File GCC/Clang mismatch: {name}")
        finally:
            listener.close()

    report = {
        "schema": 1,
        "comparisons": len(records),
        "gcc_clang_exact": True,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"comparisons": len(records), "exact": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
