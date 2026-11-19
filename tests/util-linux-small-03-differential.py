#!/usr/bin/env python3
"""Differential public-interface cases for the third util-linux Rust batch."""

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
        else:
            result.append((relative, "other", mode, ""))
    return result


def invoke(
    command: list[str], case: Case, root: Path, *, executable: Optional[Path] = None
) -> dict[str, object]:
    for name, content in case.files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        if case.unprivileged:
            path.chmod(0o666)
    if case.unprivileged:
        root.chmod(0o755)
    environment = os.environ.copy()
    environment.update({"LC_ALL": "C", "LANG": "C", "TZ": "UTC"})
    process = subprocess.run(
        [*command, *case.arguments],
        executable=str(executable) if executable is not None else None,
        cwd=root,
        env=environment,
        input=case.stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=15,
        preexec_fn=drop_privileges if case.unprivileged and os.geteuid() == 0 else None,
    )
    return {
        "status": process.returncode,
        "stdout": process.stdout,
        "stderr": process.stderr,
        "tree": tree(root),
    }


def cases() -> list[Case]:
    applets = (
        "swaplabel", "lsirq", "newgrp", "uuidgen", "switch_root",
        "raw", "renice", "ionice", "fdformat", "copyfilerange",
    )
    common = [Case(applet, (option,)) for applet in applets for option in ("--help", "--version")]
    interrupts = (
        b"           CPU0       CPU1\n"
        b"  0:         10         20   IO-APIC   2-edge      timer\n"
        b"  8:          1          2   IO-APIC   8-edge      rtc0\n"
    )
    return common + [
        Case("swaplabel"),
        Case("swaplabel", ("device",), files={"device": b"not swap\n"}),
        Case("swaplabel", ("--label", "rustbox", "device"), files={"device": b"not swap\n"}),
        Case("lsirq", ("--input", "interrupts"), files={"interrupts": interrupts}),
        Case("lsirq", ("--input", "interrupts", "--noheadings", "--output", "IRQ,TOTAL,NAME"), files={"interrupts": interrupts}),
        Case("lsirq", ("--input", "missing")),
        Case("newgrp", ("rustbox-group-does-not-exist",), unprivileged=True),
        Case("newgrp", ("-", "rustbox-group-does-not-exist"), unprivileged=True),
        Case("uuidgen", ("--sha1", "--namespace", "@dns", "--name", "rustbox")),
        Case("uuidgen", ("--md5", "--namespace", "@url", "--name", "https://rustbox.invalid/")),
        Case("uuidgen", ("--count", "3", "--sha1", "--namespace", "@oid", "--name", "1.2.3")),
        Case("switch_root"),
        Case("switch_root", ("new-root", "/bin/true"), unprivileged=True),
        Case("raw"),
        Case("raw", ("-qa",)),
        Case("raw", ("/dev/raw/raw1", "/dev/null"), unprivileged=True),
        Case("renice"),
        Case("renice", ("--priority", "0", "--pid", "999999")),
        Case("renice", ("--priority", "bad", "--pid", "1")),
        Case("ionice"),
        Case("ionice", ("--class", "idle", "/bin/sh", "-c", "printf ionice")),
        Case("ionice", ("--pid", "999999")),
        Case("ionice", ("--class", "invalid", "/bin/true")),
        Case("fdformat"),
        Case("fdformat", ("device",), files={"device": b"not a floppy\n"}),
        Case("fdformat", ("--from", "bad", "device"), files={"device": b"x"}),
        Case("copyfilerange"),
        Case("copyfilerange", ("source", "destination", "0:0:5"), files={"source": b"hello world"}),
        Case("copyfilerange", ("source", "destination", "2:3:4", "6:0:5"), files={"source": b"0123456789abc", "destination": b"xxxxxxxxxx"}),
        Case("copyfilerange", ("--verbose", "source", "destination", "0:0:0"), files={"source": b"all bytes"}),
        Case("copyfilerange", ("source", "destination", "bad"), files={"source": b"x"}),
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
            failures.append({
                "case": number,
                "applet": case.applet,
                "arguments": case.arguments,
                "canonical": canonical,
                "hybrid": hybrid,
            })
    result = {"schema": 1, "cases": len(all_cases), "passed": len(all_cases) - len(failures), "failures": failures}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, default=lambda value: value.decode("utf-8", "backslashreplace")) + "\n")
    print(json.dumps({"cases": result["cases"], "passed": result["passed"]}))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
