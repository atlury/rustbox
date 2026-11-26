#!/usr/bin/env python3
"""Run pkgconf's installed-tool fixture runner on the actual Rustbox executable."""
# SPDX-License-Identifier: ISC
import argparse
import json
from pathlib import Path
import shlex
import shutil
import subprocess
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
NAMES = ("pkgconf", "pkg-config", "bomtool", "pccritic", "spdxtool")


def entrypoints(elf, work, mode):
    folder = work / mode
    folder.mkdir()
    for name in NAMES:
        entry = folder / name
        if mode == "applet":
            entry.symlink_to(elf)
        else:
            entry.write_text("#!/bin/sh\nexec " + shlex.quote(str(elf)) + " " + name + ' "$@"\n')
            entry.chmod(0o755)
    return folder


def fixtures(elf, work):
    root = Path("/rustbox-pkgconf")
    runner = root / "normalized-gcc-static/test-runner"
    src = root / "normalized-source"
    suites = sorted(d for d in (src / "t").iterdir() if d.is_dir())
    if len(suites) != 14:
        raise ValueError("expected all fourteen upstream fixture suites")
    outcomes = {}
    for mode in ("applet", "subcommand"):
        folder = entrypoints(elf, work, mode)
        for suite in suites:
            result = subprocess.run([runner, "--test-fixtures", src / "tests", "--tool-dir", folder, suite],
                                    cwd=work, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
            if result.returncode:
                raise ValueError((mode, suite.name, result.stdout[-4096:]))
            rows = sorted(line for line in result.stdout.decode().splitlines() if line.startswith(("PASS: ", "SKIP: ")))
            if not rows or len(rows) != len(list(suite.glob("*.test"))):
                raise ValueError((mode, suite.name, "missing upstream results"))
            if outcomes.setdefault(suite.name, rows) != rows:
                raise ValueError((mode, suite.name, "dispatch modes differ"))
    return outcomes


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf", type=Path)
    args = parser.parse_args()
    with TemporaryDirectory() as temp:
        work = Path(temp)
        elf = work / "rustbox"
        shutil.copy2(args.elf.resolve(strict=True), elf)
        print(json.dumps(fixtures(elf, work), indent=2, sort_keys=True))
