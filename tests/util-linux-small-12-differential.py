#!/usr/bin/env python3
"""Differential public-interface cases for the twelfth util-linux Rust batch."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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
    files: dict[str, Optional[bytes]] = field(default_factory=dict)
    unprivileged: bool = False


def drop_privileges() -> None:
    os.setgid(65534)
    os.setuid(65534)


def tree(root: Path) -> list[tuple[object, ...]]:
    result = []
    for path in sorted(root.rglob("*")):
        relative = str(path.relative_to(root))
        status = path.lstat()
        mode = stat.S_IMODE(status.st_mode)
        if path.is_file():
            result.append((relative, "file", mode, status.st_nlink, status.st_size, hashlib.sha256(path.read_bytes()).hexdigest()))
        elif path.is_dir():
            result.append((relative, "directory", mode, ""))
    return result


def invoke(command: list[str], case: Case, root: Path, *, executable: Optional[Path] = None) -> dict[str, object]:
    for name, content in case.files.items():
        path = root / name
        if content is None:
            path.mkdir(parents=True, exist_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    for path in sorted(root.rglob("*"), reverse=True):
        os.utime(path, (1, 1), follow_symlinks=False)
    if case.unprivileged:
        root.chmod(0o755)
        for path in root.rglob("*"):
            path.chmod(0o755 if path.is_dir() else 0o644)
    environment = os.environ.copy()
    environment.update({"LC_ALL": "C", "LANG": "C", "TZ": "UTC", "TERM": "xterm"})
    process = subprocess.run(
        [*command, *case.arguments], executable=str(executable) if executable else None,
        cwd=root, env=environment, input=case.stdin, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=20,
        preexec_fn=drop_privileges if case.unprivileged and os.geteuid() == 0 else None,
    )
    stdout = process.stdout
    if case.applet == "hardlink":
        stdout = re.sub(br"Duration:\s+[0-9.]+ seconds", b"Duration: <elapsed> seconds", stdout)
    return {"status": process.returncode, "stdout": stdout, "stderr": process.stderr, "tree": tree(root)}


def cases() -> list[Case]:
    applets = ("cal", "dmesg", "fsck.minix", "hardlink", "irqtop", "lsipc", "more", "mount", "pg", "umount")
    common = [Case(applet, (option,)) for applet in applets for option in ("--help", "--version")]
    text = b"one\n\n\ntwo\nthree\n"
    return common + [
        Case("cal", ("1", "2000")),
        Case("cal", ("--iso", "12", "2024")),
        Case("cal", ("--julian", "2", "2000")),
        Case("cal", ("--reform", "1752", "9", "1752")),
        Case("cal", ("--months", "3", "6", "2025")),
        Case("dmesg", ("--file", "empty"), files={"empty": b""}),
        Case("dmesg", ("--decode", "--file", "empty"), files={"empty": b""}),
        Case("dmesg", ("--level", "invalid", "--file", "empty"), files={"empty": b""}),
        Case("dmesg", ("--facility", "invalid", "--file", "empty"), files={"empty": b""}),
        Case("fsck.minix"),
        Case("fsck.minix", ("missing",)),
        Case("fsck.minix", ("tiny",), files={"tiny": b"\0" * 1024}),
        Case("hardlink", ("--dry-run", "."), files={"a": b"same", "b": b"same"}),
        Case("hardlink", ("."), files={"a": b"same", "b": b"same"}),
        Case("hardlink", ("--ignore-time", "."), files={"a": b"same", "b": b"same"}),
        Case("hardlink", ("."), files={"a": b"left", "b": b"right"}),
        Case("hardlink", ("--exclude", "sub", "."), files={"a": b"same", "sub/b": b"same"}),
        Case("irqtop", ("--output", "invalid")),
        Case("irqtop", ("--sort", "invalid")),
        Case("lsipc", ("--id", "invalid")),
        Case("lsipc", ("--output", "INVALID")),
        Case("lsipc", ("--shmems", "--id", "999999")),
        Case("lsipc", ("--queues", "--id", "999999")),
        Case("more", ("input",), files={"input": text}),
        Case("more", ("-s", "input"), files={"input": text}),
        Case("more", ("-5", "input"), files={"input": text}),
        Case("more", stdin=text),
        Case("mount", ("--fake", "--no-mtab", "-t", "tmpfs", "tmpfs", "target"), files={"target": None}, unprivileged=True),
        Case("mount", ("--fake", "--no-mtab", "--bind", "source", "target"), files={"source": None, "target": None}, unprivileged=True),
        Case("mount", ("--fake", "--no-mtab", "missing", "target"), files={"target": None}, unprivileged=True),
        Case("pg", ("input",), files={"input": text}),
        Case("pg", ("-5", "input"), files={"input": text}),
        Case("pg", ("+2", "input"), files={"input": text}),
        Case("umount", ("--fake", "--no-mtab", "target"), files={"target": None}, unprivileged=True),
        Case("umount", ("--fake", "--no-mtab", "missing"), unprivileged=True),
        Case("umount", ("--fake", "--no-mtab", "--recursive", "target"), files={"target": None}, unprivileged=True),
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
