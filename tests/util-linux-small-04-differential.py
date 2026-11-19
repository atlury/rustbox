#!/usr/bin/env python3
"""Differential public-interface cases for the fourth util-linux Rust batch."""

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
from typing import Optional


@dataclass(frozen=True)
class Case:
    applet: str
    arguments: tuple[str, ...] = ()
    stdin: bytes = b""
    files: dict[str, bytes] = field(default_factory=dict)
    directories: tuple[str, ...] = ()
    unprivileged: bool = False


def drop_privileges() -> None:
    os.setgid(65534)
    os.setuid(65534)


def tree(root: Path) -> list[tuple[str, str, int, str]]:
    result = []
    for path in sorted(root.rglob("*")):
        relative = str(path.relative_to(root))
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_symlink():
            result.append((relative, "symlink", mode, os.readlink(path)))
        elif path.is_file():
            result.append((relative, "file", mode, hashlib.sha256(path.read_bytes()).hexdigest()))
        elif path.is_dir():
            result.append((relative, "directory", mode, ""))
    return result


def invoke(command: list[str], case: Case, root: Path, *, executable: Optional[Path] = None) -> dict[str, object]:
    for name in case.directories:
        (root / name).mkdir(parents=True, exist_ok=True)
    for name, content in case.files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    if case.unprivileged:
        root.chmod(0o755)
    environment = os.environ.copy()
    environment.update({"LC_ALL": "C", "LANG": "C", "TZ": "UTC"})
    process = subprocess.run(
        [*command, *case.arguments], executable=str(executable) if executable else None,
        cwd=root, env=environment, input=case.stdin, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=15,
        preexec_fn=drop_privileges if case.unprivileged and os.geteuid() == 0 else None,
    )
    return {"status": process.returncode, "stdout": process.stdout, "stderr": process.stderr, "tree": tree(root)}


def cases() -> list[Case]:
    applets = ("taskset", "mountpoint", "chsh", "waitpid", "colcrt", "getino", "ipcmk", "bits", "swapoff", "uclampset")
    common = [Case(applet, (option,)) for applet in applets for option in ("--help", "--version")]
    return common + [
        Case("taskset"),
        Case("taskset", ("--pid", "999999")),
        Case("taskset", ("--cpu-list", "--pid", "999999")),
        Case("taskset", ("invalid", "/bin/true")),
        Case("mountpoint", ("/",)),
        Case("mountpoint", ("dir",), directories=("dir",)),
        Case("mountpoint", ("--quiet", "dir"), directories=("dir",)),
        Case("mountpoint", ("--fs-devno", "dir"), directories=("dir",)),
        Case("mountpoint", ("missing",)),
        Case("chsh", ("--list-shells",)),
        Case("chsh", ("--shell", "/bin/sh", "rustbox-user-does-not-exist"), unprivileged=True),
        Case("waitpid", ("--timeout", "0", "999999")),
        Case("waitpid", ("--exited", "999999")),
        Case("waitpid", ("--count", "bad", "999999")),
        Case("colcrt", stdin=b"plain text\nsecond line\n"),
        Case("colcrt", ("--no-underlining",), stdin=b"a\b_\n"),
        Case("colcrt", ("--half-lines",), stdin=b"first\nsecond\n"),
        Case("getino", ("1",)),
        Case("getino", ("--print-pid", "1",)),
        Case("getino", ("--mntns", "1",)),
        Case("getino", ("999999",)),
        Case("ipcmk"),
        Case("ipcmk", ("--shmem", "invalid")),
        Case("ipcmk", ("--mode", "invalid", "--shmem", "1")),
        Case("bits", ("0xeec2",)),
        Case("bits", ("--list", "0xeec2")),
        Case("bits", ("--binary", "1,3,7")),
        Case("bits", ("--grouped-mask", "1,31,32,63")),
        Case("bits", ("--list",), stdin=b"0xff\n0x100\n"),
        Case("bits", ("invalid",)),
        Case("swapoff"),
        Case("swapoff", ("missing",), unprivileged=True),
        Case("swapoff", ("--all", "--verbose"), unprivileged=True),
        Case("uclampset"),
        Case("uclampset", ("--pid", "999999")),
        Case("uclampset", ("--min", "invalid", "/bin/true")),
        Case("uclampset", ("--min", "0", "--max", "1024", "/bin/true"), unprivileged=True),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-directory", type=Path, required=True)
    parser.add_argument("--hybrid", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    failures = []
    all_cases = cases()
    for number, case in enumerate(all_cases, 1):
        with tempfile.TemporaryDirectory(prefix="rustbox-util-c-") as left, tempfile.TemporaryDirectory(prefix="rustbox-util-r-") as right:
            canonical = invoke([case.applet], case, Path(left), executable=args.canonical_directory / case.applet)
            hybrid = invoke([str(args.hybrid), case.applet], case, Path(right))
        if canonical != hybrid:
            failures.append({"case": number, "applet": case.applet, "arguments": case.arguments, "canonical": canonical, "hybrid": hybrid})
    result = {"schema": 1, "cases": len(all_cases), "passed": len(all_cases) - len(failures), "failures": failures}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, default=lambda value: value.decode("utf-8", "backslashreplace")) + "\n")
    print(json.dumps({"cases": result["cases"], "passed": result["passed"]}))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
