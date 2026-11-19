#!/usr/bin/env python3
"""Differential public-interface cases for the first util-linux Rust batch."""

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
    locale: str = "C"
    nondeterministic_cookie: bool = False
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
    env = os.environ.copy()
    env.update({"LC_ALL": case.locale, "LANG": case.locale, "TZ": "UTC"})
    process = subprocess.run(
        [*command, *case.arguments],
        executable=str(executable) if executable is not None else None,
        cwd=root,
        env=env,
        input=case.stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        preexec_fn=drop_privileges if case.unprivileged and os.geteuid() == 0 else None,
    )
    return {
        "status": process.returncode,
        "stdout": process.stdout,
        "stderr": process.stderr,
        "tree": tree(root),
    }


def cases() -> list[Case]:
    common = [
        Case(applet, (option,))
        for applet in ("line", "setpgid", "exch", "ctrlaltdel", "setsid", "choom", "fadvise", "colrm", "mcookie", "rev")
        for option in ("--help", "--version")
    ]
    return common + [
        Case("line"),
        Case("line", stdin=b"alpha\nbeta\n"),
        Case("line", stdin=b"unterminated"),
        Case("line", stdin="åβ\nrest\n".encode(), locale="en_US.UTF-8"),
        Case("colrm", stdin=b"abcdef\n"),
        Case("colrm", ("2",), stdin=b"abcdef\n"),
        Case("colrm", ("2", "4"), stdin=b"abcdef\n"),
        Case("colrm", ("0",), stdin=b"abcdef\n"),
        Case("colrm", ("2", "4"), stdin="åβγδε\n".encode(), locale="en_US.UTF-8"),
        Case("rev", stdin=b"abc\ndef\n"),
        Case("rev", ("-0",), stdin=b"abc\x00def\x00"),
        Case("rev", ("input",), files={"input": b"abc\ndef\n"}),
        Case("rev", ("missing",)),
        Case("rev", stdin="åβγ\n".encode(), locale="en_US.UTF-8"),
        Case("setpgid", ("/bin/sh", "-c", "printf grouped")),
        Case("setpgid", ("/bin/sh", "-c", "exit 7")),
        Case("setpgid"),
        Case("setsid", ("/bin/sh", "-c", "printf session")),
        Case("setsid", ("--wait", "/bin/sh", "-c", "exit 7")),
        Case("setsid"),
        Case("exch", ("left", "right"), files={"left": b"L", "right": b"R"}),
        Case("exch", ("left", "missing"), files={"left": b"L"}),
        Case("exch"),
        Case("ctrlaltdel", ("invalid",)),
        Case("ctrlaltdel"),
        Case("ctrlaltdel", ("hard",), unprivileged=True),
        Case("ctrlaltdel", ("soft",), unprivileged=True),
        Case("choom", ("-p", "1")),
        Case("choom", ("-n", "0", "--", "/bin/sh", "-c", "printf oom")),
        Case("choom"),
        Case("fadvise", ("data",), files={"data": b"0123456789"}),
        Case("fadvise", ("--advice", "sequential", "--offset", "2", "--length", "4", "data"), files={"data": b"0123456789"}),
        Case("fadvise", ("--advice", "invalid", "data"), files={"data": b"x"}),
        Case("fadvise"),
        Case("mcookie", ("--file", "missing"), nondeterministic_cookie=True),
        Case("mcookie", ("--max-size", "invalid")),
        Case("mcookie", ("--file", "seed"), files={"seed": b"fixed seed\n"}, nondeterministic_cookie=True),
    ]


def equivalent(case: Case, canonical: dict[str, object], hybrid: dict[str, object]) -> bool:
    if case.nondeterministic_cookie:
        def cookie(result: dict[str, object]) -> bool:
            output = result["stdout"].strip()
            return result["status"] == 0 and len(output) == 32 and all(byte in b"0123456789abcdef" for byte in output)
        return cookie(canonical) and cookie(hybrid) and canonical["stderr"] == hybrid["stderr"] and canonical["tree"] == hybrid["tree"]
    return canonical == hybrid


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
            canonical = invoke(
                [case.applet],
                case,
                Path(left),
                executable=args.canonical_directory / case.applet,
            )
            hybrid = invoke([str(args.hybrid), case.applet], case, Path(right))
        if not equivalent(case, canonical, hybrid):
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
