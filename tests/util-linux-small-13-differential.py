#!/usr/bin/env python3
"""Differential public-interface cases for the thirteenth util-linux Rust batch."""

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
    if case.applet == "hwclock":
        stdout = re.sub(br"System Time: [-+0-9.]+", b"System Time: <sampled>", stdout)
    return {"status": process.returncode, "stdout": stdout, "stderr": process.stderr, "tree": tree(root)}


def cases() -> list[Case]:
    applets = ("chfn", "fsck", "hexdump", "hwclock", "lscpu", "lslogins", "lsns", "script", "swapon", "unshare")
    common = [Case(applet, (option,)) for applet in applets for option in ("--help", "--version")]
    data = b"\x00\x01hello\nworld\xff"
    return common + [
        Case("chfn", ("--list-shells",)),
        Case("chfn", ("--full-name", "Test User", "definitely-missing-user"), unprivileged=True),
        Case("chfn", ("--phone", "invalid!", "definitely-missing-user"), unprivileged=True),
        Case("fsck", ("-N", "missing-device")),
        Case("fsck", ("-A", "-N")),
        Case("fsck", ("-N", "-t", "ext4", "missing-device")),
        Case("fsck", ("-N", "-C", "0", "missing-device")),
        Case("hexdump", ("-C",), stdin=data),
        Case("hexdump", ("-x", "input"), files={"input": data}),
        Case("hexdump", ("-n", "7", "-C", "input"), files={"input": data}),
        Case("hexdump", ("-s", "2", "-C", "input"), files={"input": data}),
        Case("hexdump", ("-e", '1/1 "%02x "', "input"), files={"input": data}),
        Case("hwclock", ("--predict", "--date", "2020-01-02 03:04:05")),
        Case("hwclock", ("--show", "--test"), unprivileged=True),
        Case("hwclock", ("--get", "--test"), unprivileged=True),
        Case("lscpu"),
        Case("lscpu", ("--json",)),
        Case("lscpu", ("--parse=CPU,NODE,SOCKET,CORE",)),
        Case("lscpu", ("--extended=CPU,NODE,SOCKET,CORE",)),
        Case("lscpu", ("--caches=NAME,ONE-SIZE,ALL-SIZE",)),
        Case("lslogins", ("--output", "USER,UID")),
        Case("lslogins", ("--noheadings", "--output", "USER,UID")),
        Case("lslogins", ("--logins", "root", "--output", "USER,UID,GID")),
        Case("lslogins", ("--groups", "0", "--output", "USER,UID")),
        Case("lslogins", ("--system-accs", "--output", "USER,UID")),
        Case("lsns", ("--noheadings", "--output", "NS,TYPE,PATH")),
        Case("lsns", ("--json", "--output", "NS,TYPE")),
        Case("lsns", ("--type", "pid", "--output", "NS,TYPE,NPROCS")),
        Case("lsns", ("--type", "invalid")),
        Case("script", ("--quiet", "--command", "/bin/true", "/dev/null")),
        Case("script", ("--quiet", "--return", "--command", "/bin/false", "/dev/null")),
        Case("script", ("--quiet", "--command", "printf stable", "/dev/null")),
        Case("swapon", ("--show",)),
        Case("swapon", ("--show", "--noheadings")),
        Case("swapon", ("--show", "--output", "NAME,TYPE,SIZE,USED,PRIO")),
        Case("swapon", ("--summary",)),
        Case("unshare", ("--user", "/bin/true"), unprivileged=True),
        Case("unshare", ("--map-root-user", "--user", "/bin/true"), unprivileged=True),
        Case("unshare", ("--mount", "--propagation", "invalid", "/bin/true"), unprivileged=True),
        Case("unshare", ("--setuid", "invalid", "/bin/true"), unprivileged=True),
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
