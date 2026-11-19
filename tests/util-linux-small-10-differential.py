#!/usr/bin/env python3
"""Differential public-interface cases for the tenth util-linux Rust batch."""

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
    applets = ("enosys", "ipcs", "last", "lastb", "lsclocks", "lslocks", "lsmem", "mkfs.minix", "mkswap", "setterm", "uuidd")
    common = [Case(applet, (option,)) for applet in applets for option in ("--help", "--version")]
    wtmp = Path("/rustbox-util-linux-source/util-linux-2.42.4/tests/ts/utmp/wtmp-a.LE").read_bytes()
    return common + [
        Case("enosys"),
        Case("enosys", ("--list",)),
        Case("enosys", ("--list-ioctl",)),
        Case("enosys", ("--dump",)),
        Case("ipcs"),
        Case("ipcs", ("--all",)),
        Case("ipcs", ("--limits",)),
        Case("ipcs", ("--summary",)),
        Case("ipcs", ("--shmems", "--time")),
        Case("ipcs", ("--id", "invalid")),
        Case("last", ("-f", "empty"), files={"empty": b""}),
        Case("last", ("-R", "-f", "wtmp"), files={"wtmp": wtmp}),
        Case("last", ("--time-format", "iso", "-R", "-f", "wtmp"), files={"wtmp": wtmp}),
        Case("last", ("--since", "2013-08-28 02:20", "--until", "2013-08-28 08:20", "-R", "-f", "wtmp"), files={"wtmp": wtmp}),
        Case("last", ("--time-format", "invalid", "-f", "empty"), files={"empty": b""}),
        Case("lastb", ("-f", "empty"), files={"empty": b""}),
        Case("lastb", ("-R", "-f", "wtmp"), files={"wtmp": wtmp}),
        Case("lsclocks", ("--no-discover-dynamic", "--no-discover-rtc", "--output", "TYPE,ID,CLOCK,NAME")),
        Case("lsclocks", ("--no-discover-dynamic", "--no-discover-rtc", "--json", "--output", "TYPE,ID,NAME")),
        Case("lsclocks", ("--time", "invalid")),
        Case("lslocks", ("--pid", "999999", "--raw", "--noheadings")),
        Case("lslocks", ("--pid", "999999", "--output", "PID,COMMAND,TYPE")),
        Case("lslocks", ("--pid", "999999", "--json", "--output", "PID,PATH")),
        Case("lslocks", ("--output", "INVALID")),
        Case("lsmem", ("--summary",)),
        Case("lsmem", ("--json", "--output", "RANGE,SIZE,STATE")),
        Case("lsmem", ("--pairs", "--output", "RANGE,SIZE")),
        Case("lsmem", ("--raw", "--output", "RANGE,SIZE,NODE")),
        Case("lsmem", ("--split", "INVALID")),
        Case("mkfs.minix"),
        Case("mkfs.minix", ("missing",)),
        Case("mkfs.minix", ("tiny",), files={"tiny": b"\0" * 1024}),
        Case("mkswap"),
        Case("mkswap", ("missing",)),
        Case("mkswap", ("tiny",), files={"tiny": b"\0" * 1024}),
        Case("mkswap", ("-q", "-F", "-U", "4c08e1cd-3c82-46bf-a55b-0c3270d6dfeb", "-L", "label", "swapfile"), files={"swapfile": b"\0" * 40960}),
        Case("setterm"),
        Case("setterm", ("--term", "dumb", "--bold", "on")),
        Case("setterm", ("--term", "xterm", "--linewrap", "off")),
        Case("setterm", ("--foreground", "invalid")),
        Case("uuidd", ("--socket", "missing.sock", "--kill")),
        Case("uuidd", ("--socket", "missing.sock", "--time")),
        Case("uuidd", ("--socket", "missing.sock", "--random", "--uuids", "invalid")),
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
            canonical_body = "last" if case.applet == "lastb" else case.applet
            canonical = invoke([case.applet], case, Path(left), executable=args.canonical_directory / canonical_body)
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
