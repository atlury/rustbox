#!/usr/bin/env python3
"""Compare independent GCC and Clang builds of LZ4's public command names."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Case:
    name: str
    applet: str
    arguments: tuple[str, ...]
    files: dict[str, bytes] = field(default_factory=dict)
    setup: tuple[tuple[str, tuple[str, ...]], ...] = ()
    stdin: bytes = b""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot(root: Path) -> list[dict[str, object]]:
    records = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        metadata = path.stat()
        records.append({
            "path": path.relative_to(root).as_posix(),
            "mode": stat.S_IMODE(metadata.st_mode),
            "bytes": metadata.st_size,
            "sha256": digest(path.read_bytes()),
        })
    return records


def invoke(directory: Path, case: Case) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="rustbox-lz4-differential-") as temporary:
        root = Path(temporary)
        for name, content in case.files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        environment = os.environ.copy()
        environment.update({"LC_ALL": "C", "LANG": "C", "TZ": "UTC", "TERM": "dumb"})
        for applet, arguments in case.setup:
            setup = subprocess.run(
                [str(directory / applet), *arguments], cwd=root, env=environment,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=30,
            )
            if setup.returncode != 0:
                raise RuntimeError(f"setup {applet} {arguments!r} failed: {setup.stderr!r}")
        process = subprocess.run(
            [str(directory / case.applet), *case.arguments], cwd=root,
            env=environment, input=case.stdin, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=30,
        )
        return {
            "status": process.returncode,
            "stdout_sha256": digest(process.stdout),
            "stdout_length": len(process.stdout),
            "stderr_sha256": digest(process.stderr),
            "stderr_length": len(process.stderr),
            "tree": snapshot(root),
        }


def cases() -> list[Case]:
    text = (b"the quick brown fox jumps over the lazy dog\n" * 257)
    binary = bytes(range(256)) * 33
    randomish = bytes((index * 73 + 19) & 255 for index in range(32771))
    base = {"text": text, "binary": binary, "random": randomish, "empty": b""}
    return [
        Case("help-short", "lz4", ("-h",)),
        Case("help-long", "lz4", ("--help",)),
        Case("help-advanced", "lz4", ("-H",)),
        Case("version", "lz4", ("--version",)),
        Case("lz4c-help", "lz4c", ("--help",)),
        Case("unlz4-help", "unlz4", ("--help",)),
        Case("lz4cat-help", "lz4cat", ("--help",)),
        Case("compress-text", "lz4", ("text", "text.lz4"), files=base),
        Case("compress-binary", "lz4", ("binary", "binary.lz4"), files=base),
        Case("compress-empty", "lz4", ("empty", "empty.lz4"), files=base),
        Case("compress-high", "lz4", ("-12", "random", "high.lz4"), files=base),
        Case("compress-fast", "lz4", ("--fast=9", "text", "fast.lz4"), files=base),
        Case("compress-independent", "lz4", ("-B4", "-BD", "-BX", "text", "independent.lz4"), files=base),
        Case("compress-legacy", "lz4c", ("-l", "text", "legacy.lz4"), files=base),
        Case("compress-stdout", "lz4", ("-c", "binary"), files=base),
        Case("compress-stdin", "lz4", ("-c", "-"), stdin=text),
        Case("decompress-file", "lz4", ("-d", "text.lz4", "decoded"), files=base,
             setup=(("lz4", ("text", "text.lz4")),)),
        Case("decompress-stdout", "lz4", ("-d", "-c", "binary.lz4"), files=base,
             setup=(("lz4", ("binary", "binary.lz4")),)),
        Case("unlz4-file", "unlz4", ("text.lz4", "decoded"), files=base,
             setup=(("lz4", ("text", "text.lz4")),)),
        Case("lz4cat-file", "lz4cat", ("text.lz4",), files=base,
             setup=(("lz4", ("text", "text.lz4")),)),
        Case("list-frame", "lz4", ("--list", "text.lz4"), files=base,
             setup=(("lz4", ("text", "text.lz4")),)),
        Case("list-legacy", "lz4", ("--list", "legacy.lz4"), files=base,
             setup=(("lz4", ("-l", "text", "legacy.lz4")),)),
        Case("multiple-inputs", "lz4", ("-m", "text", "binary"), files=base),
        Case("force-output", "lz4", ("-f", "text", "output.lz4"), files={**base, "output.lz4": b"old"}),
        Case("missing-input", "lz4", ("missing", "output.lz4")),
        Case("invalid-frame", "lz4", ("-d", "-c", "invalid"), files={"invalid": b"not an lz4 frame\n"}),
        Case("unknown-option", "lz4", ("--definitely-invalid",)),
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
            raise RuntimeError(f"lz4/{case.name}: GCC {gcc} != Clang {clang}")
        records.append({"name": case.name, "applet": case.applet, "result": gcc})
    payload = {"schema": 1, "cases": len(records), "passed": len(records), "records": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"LZ4 canonical differential: {len(records)}/{len(records)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
