#!/usr/bin/env python3
"""Differential public-interface cases for the sixth util-linux Rust batch."""

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
    applets = ("coresched", "chcpu", "namei", "wall", "readprofile", "scriptreplay", "blkpr", "ldattach", "blockdev", "flock")
    common = [Case(applet, (option,)) for applet in applets for option in ("--help", "--version")]
    return common + [
        Case("coresched", ("get", "--source", "1")),
        Case("coresched", ("unknown",)),
        Case("coresched", ("new", "--dest", "999999"), unprivileged=True),
        Case("chcpu"),
        Case("chcpu", ("--enable", "invalid")),
        Case("chcpu", ("--dispatch", "invalid")),
        Case("chcpu", ("--enable", "999999"), unprivileged=True),
        Case("namei", ("file",), files={"file": b"payload"}),
        Case("namei", ("missing",)),
        Case("namei", ("--modes", "dir/file"), files={"dir/file": b"payload"}),
        Case("namei", ("--long", "dir"), files={"dir/file": b"payload"}),
        Case("wall", ("--bad-option",)),
        Case("wall", ("--group", "rustbox-group-does-not-exist", "message")),
        Case("wall", ("--timeout", "invalid", "message")),
        Case("readprofile"),
        Case("readprofile", ("--profile", "missing.profile", "--mapfile", "missing.map")),
        Case("readprofile", ("--multiplier", "invalid")),
        Case("readprofile", ("--info", "--profile", "empty"), files={"empty": b""}),
        Case("scriptreplay"),
        Case("scriptreplay", ("missing.timing", "missing.typescript")),
        Case("scriptreplay", ("--divisor", "invalid", "timing", "typescript"), files={"timing": b"", "typescript": b""}),
        Case("scriptreplay", ("--maxdelay", "0", "timing", "typescript"), files={"timing": b"0.000001 6\n", "typescript": b"hello\n"}),
        Case("blkpr"),
        Case("blkpr", ("device",), files={"device": b"not a block device"}, unprivileged=True),
        Case("blkpr", ("--command", "invalid", "device"), files={"device": b"x"}),
        Case("blkpr", ("--key", "invalid", "device"), files={"device": b"x"}),
        Case("ldattach"),
        Case("ldattach", ("invalid-discipline", "/dev/null"), unprivileged=True),
        Case("ldattach", ("0", "/dev/null"), unprivileged=True),
        Case("ldattach", ("--speed", "invalid", "0", "/dev/null"), unprivileged=True),
        Case("blockdev"),
        Case("blockdev", ("--getsize64", "regular"), files={"regular": b"payload"}, unprivileged=True),
        Case("blockdev", ("--report", "regular"), files={"regular": b"payload"}, unprivileged=True),
        Case("blockdev", ("--unknown", "regular"), files={"regular": b"payload"}),
        Case("flock", ("lock", "/bin/sh", "-c", "printf locked")),
        Case("flock", ("--shared", "lock", "/bin/true")),
        Case("flock", ("--nonblocking", "lock", "/bin/true")),
        Case("flock", ("--timeout", "invalid", "lock", "/bin/true")),
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
