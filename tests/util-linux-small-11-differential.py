#!/usr/bin/env python3
"""Differential public-interface cases for the eleventh util-linux Rust batch."""

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
    unprivileged: bool = False


def drop_privileges() -> None:
    os.setgid(65534)
    os.setuid(65534)


def tree(root: Path) -> list[tuple[object, ...]]:
    result = []
    for path in sorted(root.rglob("*")):
        relative = str(path.relative_to(root))
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_file():
            result.append((relative, "file", mode, path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest()))
        elif path.is_dir():
            result.append((relative, "directory", mode, ""))
    return result


def invoke(command: list[str], case: Case, root: Path, *, executable: Optional[Path] = None) -> dict[str, object]:
    for name, content in case.files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    for path in sorted(root.rglob("*"), reverse=True):
        os.utime(path, (1, 1), follow_symlinks=False)
    if case.unprivileged:
        root.chmod(0o755)
    environment = os.environ.copy()
    environment.update({"LC_ALL": "C", "LANG": "C", "TZ": "UTC", "TERM": "xterm"})
    process = subprocess.run(
        [*command, *case.arguments], executable=str(executable) if executable else None,
        cwd=root, env=environment, input=case.stdin, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=20,
        preexec_fn=drop_privileges if case.unprivileged and os.geteuid() == 0 else None,
    )
    return {"status": process.returncode, "stdout": process.stdout, "stderr": process.stderr, "tree": tree(root)}


def cases() -> list[Case]:
    applets = ("blkid", "column", "eject", "logger", "losetup", "nsenter", "partx", "setpriv", "wipefs", "zramctl")
    common = [Case(applet, (option,)) for applet in applets for option in ("--help", "--version")]
    return common + [
        Case("blkid", ("empty",), files={"empty": b""}),
        Case("blkid", ("-p", "empty"), files={"empty": b""}),
        Case("blkid", ("-p", "-o", "udev", "empty"), files={"empty": b""}),
        Case("blkid", ("-p", "missing")),
        Case("column", stdin=b"one two\nthree four\n"),
        Case("column", ("-t",), stdin=b"one two\nthree four\n"),
        Case("column", ("-s", ",", "-t"), stdin=b"one,two\nthree,four\n"),
        Case("column", ("-c", "12"), stdin=b"one two three four five\n"),
        Case("eject", ("--default",), unprivileged=True),
        Case("eject", ("--noop", "missing"), unprivileged=True),
        Case("eject", ("missing",), unprivileged=True),
        Case("logger", ("--socket", "missing.sock", "message"), unprivileged=True),
        Case("logger", ("--socket", "missing.sock", "--stderr", "message"), unprivileged=True),
        Case("logger", ("--socket", "missing.sock", "--priority", "user.info", "message"), unprivileged=True),
        Case("losetup", ("--list", "--noheadings", "--output", "NAME")),
        Case("losetup", ("--associated", "missing")),
        Case("losetup", ("--detach", "missing"), unprivileged=True),
        Case("nsenter", ("--target", "999999", "--mount", "/bin/true"), unprivileged=True),
        Case("nsenter", ("--target", "invalid"), unprivileged=True),
        Case("nsenter", ("--root=/proc/999999/root", "/bin/true"), unprivileged=True),
        Case("partx", ("--show", "missing"), unprivileged=True),
        Case("partx", ("--show", "empty"), files={"empty": b""}, unprivileged=True),
        Case("partx", ("--add", "missing"), unprivileged=True),
        Case("setpriv", ("--dump",)),
        Case("setpriv", ("--no-new-privs", "/bin/true"), unprivileged=True),
        Case("setpriv", ("--bounding-set", "invalid", "/bin/true"), unprivileged=True),
        Case("wipefs", ("--no-act", "empty"), files={"empty": b""}),
        Case("wipefs", ("--all", "--no-act", "empty"), files={"empty": b""}),
        Case("wipefs", ("--offset", "0", "empty"), files={"empty": b""}),
        Case("wipefs", ("missing",)),
        Case("zramctl", ("--output", "NAME,DISKSIZE", "--noheadings")),
        Case("zramctl", ("/dev/zram999",)),
        Case("zramctl", ("--reset", "/dev/zram999"), unprivileged=True),
        Case("zramctl", ("--algorithm", "/dev/zram999"), unprivileged=True),
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
