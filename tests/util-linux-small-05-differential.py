#!/usr/bin/env python3
"""Differential public-interface cases for the fifth util-linux Rust batch."""

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
    applets = ("look", "pipesz", "blkdiscard", "tunelp", "rename", "uuidparse", "utmpdump", "lastlog2", "scriptlive", "vipw")
    common = [Case(applet, (option,)) for applet in applets for option in ("--help", "--version")]
    words = b"Alpha\nalphabet\nbeta\nbetatron\ngamma\n"
    return common + [
        Case("look", ("beta", "words"), files={"words": words}),
        Case("look", ("--ignore-case", "alpha", "words"), files={"words": words}),
        Case("look", ("missing", "words"), files={"words": words}),
        Case("look", ("word", "missing")),
        Case("pipesz", ("--get",), stdin=b"pipe data"),
        Case("pipesz", ("--set", "4096", "--", "/bin/sh", "-c", "printf resized")),
        Case("pipesz", ("--set", "invalid", "/bin/true")),
        Case("pipesz", ("--file", "regular", "--get"), files={"regular": b"x"}),
        Case("blkdiscard"),
        Case("blkdiscard", ("device",), files={"device": b"not block\n"}, unprivileged=True),
        Case("blkdiscard", ("--offset", "bad", "device"), files={"device": b"x"}),
        Case("tunelp"),
        Case("tunelp", ("/dev/null",), unprivileged=True),
        Case("tunelp", ("missing",)),
        Case("rename", ("old", "new", "old-file"), files={"old-file": b"payload"}),
        Case("rename", ("--no-act", "old", "new", "old-file"), files={"old-file": b"payload"}),
        Case("rename", ("--all", "a", "x", "banana"), files={"banana": b"fruit"}),
        Case("rename"),
        Case("uuidparse", ("550e8400-e29b-41d4-a716-446655440000",)),
        Case("uuidparse", ("--noheadings", "--output", "UUID,VARIANT,TYPE", "550e8400-e29b-41d4-a716-446655440000")),
        Case("uuidparse", ("--json", "not-a-uuid")),
        Case("uuidparse", stdin=b"550e8400-e29b-41d4-a716-446655440000\n"),
        Case("utmpdump", ("empty",), files={"empty": b""}),
        Case("utmpdump", ("missing",)),
        Case("utmpdump", ("--reverse", "empty"), files={"empty": b""}),
        Case("lastlog2", ("--database", "missing.db", "--user", "rustbox-user-does-not-exist")),
        Case("lastlog2", ("--database", "directory",), files={"directory/file": b"x"}),
        Case("lastlog2", ("--before", "invalid")),
        Case("scriptlive"),
        Case("scriptlive", ("missing.timing", "missing.typescript")),
        Case("scriptlive", ("--divisor", "invalid", "timing", "typescript"), files={"timing": b"", "typescript": b""}),
        Case("vipw", ("--bad-option",), unprivileged=True),
        Case("vipw", ("extra",), unprivileged=True),
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
