#!/usr/bin/env python3
"""Differential public-interface cases for the final util-linux Rust batch."""

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
    stderr = process.stderr
    stderr = stderr.replace(b"/rustbox-util-linux/canonical-clang-compdb/.libs/", b"")
    return {"status": process.returncode, "stdout": process.stdout, "stderr": stderr, "tree": tree(root)}


def cases() -> list[Case]:
    applets = ("agetty", "cfdisk", "fdisk", "findmnt", "login", "lsblk", "lsfd", "runuser", "sfdisk", "su", "sulogin", "vigr")
    common = [Case(applet, (option,)) for applet in applets for option in ("--help", "--version")]
    blank_disk = b"\0" * (1024 * 1024)
    return common + [
        Case("cfdisk", ("--list", "disk.img"), files={"disk.img": blank_disk}),
        Case("fdisk", ("--list", "disk.img"), files={"disk.img": blank_disk}),
        Case("fdisk", ("--list-details", "disk.img"), files={"disk.img": blank_disk}),
        Case("findmnt", ("--list-columns",)),
        Case("findmnt", ("--fstab", "--noheadings", "--output", "TARGET,SOURCE,FSTYPE")),
        Case("findmnt", ("--kernel", "--first-only", "--target", "/")),
        Case("lsblk", ("--list-columns",)),
        Case("lsblk", ("--json", "--output", "NAME,TYPE,SIZE")),
        Case("lsfd", ("--list-columns",)),
        Case("lsfd", ("--pid", "1", "--output", "PID,COMMAND,FD,TYPE")),
        Case("runuser", ("--user", "root", "--", "/bin/true")),
        Case("sfdisk", ("--list-types",)),
        Case("sfdisk", ("--dump", "disk.img"), files={"disk.img": blank_disk}),
        Case("su", ("--shell", "/bin/sh", "--command", "exit 7", "root")),
        Case("vigr", ("--bad-option",)),
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
            canonical_name = "vipw" if case.applet == "vigr" else case.applet
            canonical = invoke([case.applet], case, Path(left), executable=args.canonical_directory / canonical_name)
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
