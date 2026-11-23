#!/usr/bin/env python3
"""Differential public-interface cases for the seventh util-linux Rust batch."""

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


def tree(root: Path, *, scrub_bfs_timestamps: bool = False) -> list[tuple[object, ...]]:
    result = []
    for path in sorted(root.rglob("*")):
        relative = str(path.relative_to(root))
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_symlink():
            result.append((relative, "symlink", mode, os.readlink(path)))
        elif path.is_file():
            content = path.read_bytes()
            # mkfs.bfs writes time(NULL) into the root inode at byte 512.
            # Canonical and hybrid commands run sequentially, so crossing a
            # one-second boundary can change only these three 32-bit fields.
            if scrub_bfs_timestamps and len(content) >= 564:
                content = content[:552] + bytes(12) + content[564:]
            result.append((relative, "file", mode, path.stat().st_size, hashlib.sha256(content).hexdigest()))
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
    return {
        "status": process.returncode,
        "stdout": process.stdout,
        "stderr": process.stderr,
        "tree": tree(root, scrub_bfs_timestamps=case.applet == "mkfs.bfs" and process.returncode == 0),
    }


def cases() -> list[Case]:
    applets = ("mkfs.bfs", "write", "getopt", "fallocate", "chrt", "fincore", "whereis", "col", "chmem", "rfkill")
    common = [Case(applet, (option,)) for applet in applets for option in ("--help", "--version")]
    return common + [
        Case("mkfs.bfs"),
        Case("mkfs.bfs", ("missing",)),
        Case("mkfs.bfs", ("tiny",), files={"tiny": b"x" * 512}),
        Case("write"),
        Case("write", ("rustbox-user-does-not-exist",)),
        Case("write", ("user", "tty", "extra")),
        Case("getopt", ("-o", "ab:", "--", "-a", "-b", "value", "tail")),
        Case("getopt", ("--long", "alpha,beta:", "--", "--alpha", "--beta=value", "tail")),
        Case("getopt", ("--shell", "bash", "-o", "a:", "--", "-a", "space value")),
        Case("getopt", ("--test",)),
        Case("getopt", ("--shell", "invalid", "-o", "a", "--")),
        Case("fallocate", ("--length", "4096", "file")),
        Case("fallocate", ("--offset", "1024", "--length", "2048", "file")),
        Case("fallocate", ("--punch-hole", "--offset", "1024", "--length", "1024", "file"), files={"file": b"x" * 4096}),
        Case("fallocate", ("--length", "invalid", "file")),
        Case("chrt"),
        Case("chrt", ("--pid", "1")),
        Case("chrt", ("--other", "0", "/bin/true")),
        Case("chrt", ("--fifo", "not-a-priority", "/bin/true")),
        Case("fincore", ("file",), files={"file": b"payload"}),
        Case("fincore", ("--bytes", "file"), files={"file": b"payload"}),
        Case("fincore", ("--json", "file"), files={"file": b"payload"}),
        Case("fincore", ("missing",)),
        Case("whereis", ("sh",)),
        Case("whereis", ("--binary", "sh",)),
        Case("whereis", ("--manual", "rustbox-name-does-not-exist",)),
        Case("whereis", ("--list",)),
        Case("col", stdin=b"one\n\bX\ntwo\rTHREE\n"),
        Case("col", ("--no-backspaces",), stdin=b"a\bX\n"),
        Case("col", ("--spaces",), stdin=b"a\tb\n"),
        Case("col", ("--tabs", "invalid"), stdin=b"x\n"),
        Case("chmem"),
        Case("chmem", ("--enable", "invalid")),
        Case("chmem", ("--disable", "1M"), unprivileged=True),
        Case("chmem", ("--blocks", "invalid", "--enable")),
        Case("rfkill"),
        Case("rfkill", ("list",)),
        Case("rfkill", ("block", "invalid-identifier"), unprivileged=True),
        Case("rfkill", ("invalid-command",)),
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
