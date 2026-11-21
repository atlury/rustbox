#!/usr/bin/env python3
"""Compare independent GCC and Clang installs of all GNU Gzip commands."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
import argparse


NAMES = (
    "gzip", "gunzip", "zcat", "uncompress", "gzexe", "zcmp", "zdiff",
    "zegrep", "zfgrep", "zforce", "zgrep", "zless", "zmore", "znew",
)


@dataclass(frozen=True)
class Setup:
    applet: str
    arguments: tuple[str, ...]
    stdout_path: str | None = None


@dataclass(frozen=True)
class Case:
    name: str
    applet: str
    arguments: tuple[str, ...]
    files: dict[str, bytes] = field(default_factory=dict)
    executable_files: tuple[str, ...] = ()
    setup: tuple[Setup, ...] = ()
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


def prepare(root: Path, directory: Path, case: Case) -> tuple[Path, Path]:
    workspace = root / "workspace"
    commands = root / "commands"
    shutil.rmtree(workspace, ignore_errors=True)
    shutil.rmtree(commands, ignore_errors=True)
    workspace.mkdir()
    commands.mkdir()
    for name in NAMES:
        (commands / name).symlink_to(directory / name)
    for name, content in case.files.items():
        path = workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        os.utime(path, (946684800, 946684800))
    for name in case.executable_files:
        (workspace / name).chmod(0o755)
    return workspace, commands


def environment(commands: Path) -> dict[str, str]:
    return {
        "LC_ALL": "C", "LANG": "C", "TZ": "UTC", "TERM": "dumb",
        "PATH": f"{commands}:/usr/bin:/bin", "PAGER": "cat", "LESS": "-FX",
    }


def invoke(directory: Path, case: Case, root: Path) -> dict[str, object]:
    workspace, commands = prepare(root, directory, case)
    env = environment(commands)
    for setup in case.setup:
        output = subprocess.PIPE
        stream = None
        if setup.stdout_path:
            stream = (workspace / setup.stdout_path).open("wb")
            output = stream
        try:
            process = subprocess.run(
                [str(commands / setup.applet), *setup.arguments], cwd=workspace,
                env=env, stdin=subprocess.DEVNULL, stdout=output,
                stderr=subprocess.PIPE, timeout=30,
            )
        finally:
            if stream:
                stream.close()
        if process.returncode != 0:
            raise RuntimeError(
                f"setup {setup.applet} {setup.arguments!r} failed: {process.stderr!r}"
            )
    process = subprocess.run(
        [str(commands / case.applet), *case.arguments], cwd=workspace, env=env,
        input=case.stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
    )
    return {
        "status": process.returncode,
        "stdout_sha256": digest(process.stdout), "stdout_length": len(process.stdout),
        "stderr_sha256": digest(process.stderr), "stderr_length": len(process.stderr),
        "tree": snapshot(workspace),
    }


def cases() -> list[Case]:
    text = b"alpha beta gamma\n" * 257
    other = b"alpha delta gamma\n" * 257
    binary = bytes(range(256)) * 31
    files = {"text": text, "other": other, "binary": binary, "empty": b""}
    result = [
        Case(f"{name}-help", name, ("--help",)) for name in NAMES
    ] + [
        Case(f"{name}-version", name, ("--version",)) for name in NAMES
    ]
    result.extend([
        Case("gzip-stdout", "gzip", ("-n", "-c", "text"), files=files),
        Case("gzip-best", "gzip", ("-n", "-9", "-c", "binary"), files=files),
        Case("gzip-fast", "gzip", ("-n", "-1", "-c", "binary"), files=files),
        Case("gzip-rsyncable", "gzip", ("-n", "--rsyncable", "-c", "text"), files=files),
        Case("gzip-file", "gzip", ("-n", "text"), files=files),
        Case("gzip-keep", "gzip", ("-n", "-k", "text"), files=files),
        Case("gzip-empty", "gzip", ("-n", "empty"), files=files),
        Case("gzip-stdin", "gzip", ("-n", "-c"), stdin=binary),
        Case("gzip-list", "gzip", ("-l", "text.gz"), files=files,
             setup=(Setup("gzip", ("-n", "-c", "text"), "text.gz"),)),
        Case("gzip-test", "gzip", ("-t", "text.gz"), files=files,
             setup=(Setup("gzip", ("-n", "-c", "text"), "text.gz"),)),
        Case("gunzip-stdout", "gunzip", ("-c", "text.gz"), files=files,
             setup=(Setup("gzip", ("-n", "-c", "text"), "text.gz"),)),
        Case("gunzip-file", "gunzip", ("text.gz",), files=files,
             setup=(Setup("gzip", ("-n", "-c", "text"), "text.gz"),)),
        Case("uncompress-stdout", "uncompress", ("-c", "text.gz"), files=files,
             setup=(Setup("gzip", ("-n", "-c", "text"), "text.gz"),)),
        Case("zcat-file", "zcat", ("text.gz",), files=files,
             setup=(Setup("gzip", ("-n", "-c", "text"), "text.gz"),)),
        Case("zcmp-same", "zcmp", ("text.gz", "copy.gz"), files=files,
             setup=(Setup("gzip", ("-n", "-c", "text"), "text.gz"),
                    Setup("gzip", ("-n", "-c", "text"), "copy.gz"))),
        Case("zcmp-different", "zcmp", ("text.gz", "other.gz"), files=files,
             setup=(Setup("gzip", ("-n", "-c", "text"), "text.gz"),
                    Setup("gzip", ("-n", "-c", "other"), "other.gz"))),
        Case("zdiff-different", "zdiff", ("text.gz", "other.gz"), files=files,
             setup=(Setup("gzip", ("-n", "-c", "text"), "text.gz"),
                    Setup("gzip", ("-n", "-c", "other"), "other.gz"))),
        Case("zgrep", "zgrep", ("-n", "beta", "text.gz"), files=files,
             setup=(Setup("gzip", ("-n", "-c", "text"), "text.gz"),)),
        Case("zegrep", "zegrep", ("-n", "alpha|gamma", "text.gz"), files=files,
             setup=(Setup("gzip", ("-n", "-c", "text"), "text.gz"),)),
        Case("zfgrep", "zfgrep", ("-n", "alpha beta", "text.gz"), files=files,
             setup=(Setup("gzip", ("-n", "-c", "text"), "text.gz"),)),
        Case("zforce", "zforce", ("compressed",), files=files,
             setup=(Setup("gzip", ("-n", "-c", "text"), "compressed"),)),
        Case("zmore", "zmore", ("text.gz",), files=files,
             setup=(Setup("gzip", ("-n", "-c", "text"), "text.gz"),)),
        Case("zless", "zless", ("text.gz",), files=files,
             setup=(Setup("gzip", ("-n", "-c", "text"), "text.gz"),)),
        Case("gzexe-compress", "gzexe", ("tool",),
             files={"tool": b"#!/bin/sh\nprintf 'payload\\n'\n"},
             executable_files=("tool",)),
        Case("missing", "gzip", ("missing",)),
        Case("invalid", "gzip", ("-dc", "invalid"), files={"invalid": b"not gzip\n"}),
    ])
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gcc-directory", type=Path, required=True)
    parser.add_argument("--clang-directory", type=Path, required=True)
    parser.add_argument("--applets", nargs="+", choices=NAMES)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    selected = set(args.applets or NAMES)
    records = []
    with tempfile.TemporaryDirectory(prefix="rustbox-gzip-differential-") as temporary:
        root = Path(temporary)
        for case in (case for case in cases() if case.applet in selected):
            gcc = invoke(args.gcc_directory.resolve(), case, root)
            clang = invoke(args.clang_directory.resolve(), case, root)
            if gcc != clang:
                raise RuntimeError(f"gzip/{case.name}: GCC {gcc} != Clang {clang}")
            records.append({"name": case.name, "applet": case.applet, "result": gcc})
    payload = {"schema": 1, "cases": len(records), "passed": len(records), "records": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"GNU Gzip canonical differential: {len(records)}/{len(records)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
