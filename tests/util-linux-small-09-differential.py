#!/usr/bin/env python3
"""Differential public-interface cases for the ninth util-linux Rust batch."""

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
        stderr=subprocess.PIPE, timeout=15,
        preexec_fn=drop_privileges if case.unprivileged and os.geteuid() == 0 else None,
    )
    return {"status": process.returncode, "stdout": process.stdout, "stderr": process.stderr, "tree": tree(root)}


def cases() -> list[Case]:
    applets = ("blkzone", "ipcrm", "fstrim", "prlimit", "fsck.cramfs", "mkfs.cramfs", "kill", "rtcwake", "wdctl", "ul")
    common = [Case(applet, (option,)) for applet in applets for option in ("--help", "--version")]
    return common + [
        Case("blkzone"),
        Case("blkzone", ("report", "regular"), files={"regular": b"payload"}, unprivileged=True),
        Case("blkzone", ("invalid", "regular"), files={"regular": b"payload"}),
        Case("ipcrm"),
        Case("ipcrm", ("--shmem-id", "2147483647"), unprivileged=True),
        Case("ipcrm", ("--queue-key", "0xffffffff"), unprivileged=True),
        Case("ipcrm", ("--semaphore-id", "invalid")),
        Case("fstrim"),
        Case("fstrim", ("path",), files={"path/file": b"payload"}, unprivileged=True),
        Case("fstrim", ("--offset", "invalid", "path"), files={"path/file": b"payload"}),
        Case("prlimit"),
        Case("prlimit", ("--pid", "1", "--nofile")),
        Case("prlimit", ("--pid", "999999", "--nproc")),
        Case("prlimit", ("--nproc=1:2", "--", "/bin/true")),
        Case("fsck.cramfs"),
        Case("fsck.cramfs", ("missing",)),
        Case("fsck.cramfs", ("image",), files={"image": b"not cramfs\n"}),
        Case("fsck.cramfs", ("--extract=out", "image"), files={"image": b"not cramfs\n"}),
        Case("mkfs.cramfs"),
        Case("mkfs.cramfs", ("missing", "image")),
        Case("mkfs.cramfs", ("tree", "image"), files={"tree/file": b"payload\n"}),
        Case("mkfs.cramfs", ("--edition", "invalid", "tree", "image"), files={"tree/file": b"payload\n"}),
        Case("kill", ("--list",)),
        Case("kill", ("--list", "TERM")),
        Case("kill", ("--table",)),
        Case("kill", ("--signal", "0", "1"), unprivileged=True),
        Case("kill", ("--signal", "invalid", "1")),
        Case("rtcwake"),
        Case("rtcwake", ("--mode", "show"), unprivileged=True),
        Case("rtcwake", ("--mode", "invalid")),
        Case("rtcwake", ("--device", "/dev/null", "--mode", "show"), unprivileged=True),
        Case("wdctl"),
        Case("wdctl", ("missing",)),
        Case("wdctl", ("/dev/null",), unprivileged=True),
        Case("wdctl", ("--output", "IDENTITY,TIMEOUT", "/dev/null"), unprivileged=True),
        Case("ul", stdin=b"plain\n"),
        Case("ul", stdin=b"_\bU underline\nX\bX bold\n"),
        Case("ul", ("--indicated",), stdin=b"_\bU underline\n"),
        Case("ul", ("--terminal", "dumb",), stdin=b"plain\n"),
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
