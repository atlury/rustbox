#!/usr/bin/env python3
"""Compare both Bison multicall entry modes and their compiled C/C++ parsers against GNU."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from bison_length_archive import selection
from check_cargo_private_inlines import ROOT, digest
from preview_bison_literal_lengths import commands


def check(link, binary):
    release = json.loads(link.read_bytes())
    record = selection.pinned()
    row = record["pilot"]
    if (release.get(selection.field) != record or release["binary"]["sha256"] != digest(binary)
            or release["source_library_sha256"].get(str(selection.candidate_path(row))) != row["candidate_sha256"]):
        raise ValueError("Bison archive or executable differs from the selected release")
    result = json.loads(subprocess.check_output([ROOT / "scripts/run_multicall_tool.sh", "python3", "-B",
                        "/work/scripts/test_bison_length_multicall.py", "--inside"],
                        env=dict(os.environ, RUSTBOX_MULTICALL_TEST_BINARY=str(binary.resolve()))))
    preview = json.loads((ROOT / "evidence/bison-literal-length-multicall.json").read_bytes())
    if result != dict(canonical=preview["canonical"], multicall_sha256=release["binary"]["sha256"]):
        raise ValueError("Bison command results differ from the qualified preview")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--link", type=Path)
    p.add_argument("--binary", type=Path)
    args = p.parse_args()
    if args.inside:
        elf = Path(os.environ["RUSTBOX_TEST_ELF"])
        with TemporaryDirectory() as tmp:
            result = dict(commands(elf, Path(tmp)), multicall_sha256=digest(elf))
    elif args.binary and args.link:
        result = check(args.link, args.binary)
    else:
        p.error("--link and --binary are required")
    print(json.dumps(result, sort_keys=True))
