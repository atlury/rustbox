#!/usr/bin/env python3
"""Differential public-interface cases for the second util-linux Rust batch."""

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
        "pivot_root", "delpart", "addpart", "findfs", "nologin",
        "resizepart", "mkfs", "fsfreeze", "isosize", "mesg",
    )
    common = [Case(applet, (option,)) for applet in applets for option in ("--help", "--version")]
    return common + [
        Case("pivot_root"),
        Case("pivot_root", ("new-root", "old-root"), unprivileged=True),
        Case("pivot_root", ("missing", "missing"), unprivileged=True),
        Case("delpart"),
        Case("delpart", ("disk", "1"), files={"disk": b"not a block device\n"}),
        Case("delpart", ("disk", "zero"), files={"disk": b"x"}),
        Case("addpart"),
        Case("addpart", ("disk", "1", "0", "512"), files={"disk": b"x"}),
        Case("addpart", ("disk", "bad", "0", "512"), files={"disk": b"x"}),
        Case("findfs"),
        Case("findfs", ("LABEL=rustbox-definitely-missing",)),
        Case("findfs", ("UUID=00000000-0000-0000-0000-000000000000",)),
        Case("findfs", ("not-a-tag",)),
        Case("nologin"),
        Case("nologin", ("ignored", "arguments")),
        Case("resizepart"),
        Case("resizepart", ("disk", "1", "4096"), files={"disk": b"x"}),
        Case("resizepart", ("disk", "bad", "4096"), files={"disk": b"x"}),
        Case("mkfs"),
        Case("mkfs", ("-t", "rustbox-no-such-filesystem", "image"), files={"image": b"x"}),
        Case("mkfs", ("-V",)),
        Case("fsfreeze"),
        Case("fsfreeze", ("--freeze", "file"), files={"file": b"x"}),
        Case("fsfreeze", ("--freeze", "--unfreeze", "file"), files={"file": b"x"}),
        Case("isosize"),
        Case("isosize", ("image",), files={"image": b""}),
        Case("isosize", ("--sector", "bad", "image"), files={"image": b"x"}),
        Case("mesg"),
        Case("mesg", ("y",)),
        Case("mesg", ("invalid",)),
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
