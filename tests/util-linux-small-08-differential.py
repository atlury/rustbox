#!/usr/bin/env python3
"""Differential public-interface cases for all canonical setarch aliases."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class Case:
    applet: str
    arguments: tuple[str, ...] = ()


def invoke(command: list[str], case: Case, root: Path, *, executable: Optional[Path] = None) -> dict[str, object]:
    environment = os.environ.copy()
    environment.update({"LC_ALL": "C", "LANG": "C", "TZ": "UTC"})
    process = subprocess.run(
        [*command, *case.arguments], executable=str(executable) if executable else None,
        cwd=root, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=15,
    )
    return {"status": process.returncode, "stdout": process.stdout, "stderr": process.stderr}


def cases() -> list[Case]:
    aliases = (
        "i386", "ia64", "linux32", "linux64", "mips", "mips32", "mips64",
        "parisc", "parisc32", "parisc64", "ppc", "ppc32", "ppc64", "s390",
        "s390x", "setarch", "sparc", "sparc32", "sparc32bash", "sparc64",
        "uname26", "x86_64",
    )
    common = [Case(applet, (option,)) for applet in aliases for option in ("--help", "--version")]
    return common + [
        Case("setarch", ("--list",)),
        Case("setarch", ("--show=0",)),
        Case("setarch", ("--show=0x00800000",)),
        Case("setarch", ("qubit", "/bin/true")),
        Case("x86_64", ("/bin/printf", "alias-ok")),
        Case("linux32", ("/bin/uname", "-m")),
        Case("linux64", ("/bin/uname", "-m")),
        Case("uname26", ("/bin/uname", "-r")),
        Case("i386", ("/bin/true",)),
        Case("sparc", ("/bin/true",)),
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
            canonical_executable = args.canonical_directory / case.applet
            if not canonical_executable.exists():
                canonical_executable = args.canonical_directory / "setarch"
            canonical = invoke([case.applet], case, Path(left), executable=canonical_executable)
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
