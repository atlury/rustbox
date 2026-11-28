#!/usr/bin/env python3
"""Verify file's bounded compression header matcher in both public multicall invocation forms."""
# SPDX-License-Identifier: BSD-2-Clause
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys

from check_cargo_private_inlines import ROOT
from link_rustbox_multicall import namespace_file_library
from preview_cargo_multicall import preview


def namespace(path, residues, release, stage):
    if residues:
        raise ValueError("unexpected file archive linkage inputs")
    archive, exports = namespace_file_library(path, stage)
    if exports != release["file_namespaced_symbols"]:
        raise ValueError("file C exports differ after the conversion")
    return archive, []


def commands(elf, stage):
    base = Path("/rustbox-file")
    results = {}
    for mode in ("applet", "subcommand"):
        folder = stage / mode
        folder.mkdir()
        binary = folder / "file"
        if mode == "applet":
            binary.symlink_to(elf)
        else:
            binary.write_text("#!/bin/sh\nexec " + shlex.quote(str(elf)) + ' file "$@"\n')
            binary.chmod(0o755)
        for cc in ("gcc", "clang"):
            report = folder / (cc + ".json")
            subprocess.run([sys.executable, ROOT/"tests/file-oracle-differential.py",
                            "--gcc", base/("canonical-"+cc)/"src/file", "--clang", binary,
                            "--magic", base/"canonical-gcc/magic/magic", "--upstream-tests", base/"normalized-source/tests",
                            "--output", report], check=True, stdout=subprocess.DEVNULL)
            row = json.loads(report.read_bytes())
            if not row["gcc_clang_exact"] or row["comparisons"] != 174:
                raise ValueError("incomplete file command comparison")
            results[mode + "-" + cc] = row["comparisons"]
    return dict(public_command_comparisons=results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("parent", "log", "pilot", "output"):
        parser.add_argument(arg, type=Path)
    args = parser.parse_args()
    proof = json.loads((ROOT / "evidence/file-borrowed-compression-headers.json").read_bytes())
    preview(args.parent, args.log, args.pilot, args.output, proof["archive"], namespace, commands)
