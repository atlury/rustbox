#!/usr/bin/env python3
"""Repeat the canonical LZ4 commands and benchmark on a selected, SHA-bound multicall executable."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from check_cargo_private_inlines import ROOT, digest
from lz4_dictionary_archive import selection
from preview_lz4_dictionary import commands


def expected_commands(preview, elf_sha):
    fields = ("canonical_cases", "synthetic_benchmark", "cli_driver_sha256")
    return dict({name: preview[name] for name in fields}, multicall_sha256=elf_sha)


def verify_release(release, control, inventory, observed):
    preview = json.loads(selection.evidence.read_bytes())["multicall"]
    if selection.field not in release:
        raise ValueError("missing the LZ4 dictionary archive")
    selection.parent_view(release)
    row = release[selection.field]["pilot"]
    elf_sha = release["binary"]["sha256"]
    delta = inventory["lz4_dictionary_deltas"]
    if (set(delta) != {selection.key} or delta[selection.key]["raw_pointer_type_tokens"] != row["raw_pointer_types_removed"]
            or inventory["binary_sha256"] != elf_sha or observed != expected_commands(preview, elf_sha)
            or (control["binary"]["sha256"] == preview["parent"]["sha256"] and elf_sha != preview["candidate"]["sha256"])):
        raise ValueError("LZ4 source counts, executable or canonical observations differ from the selected archive")


def check(link, binary):
    raw = link.read_bytes()
    release = json.loads(raw)
    if selection.field not in release:
        raise ValueError("missing the LZ4 dictionary archive")
    selection.parent_view(release)
    tested = json.loads(selection.evidence.read_bytes())["multicall"]
    elf_sha = digest(binary)
    if release["binary"]["sha256"] != elf_sha:
        raise ValueError("the saved Linux executable differs from its release")
    output = subprocess.check_output([ROOT / "scripts/run_multicall_tool.sh", "python3", "-B",
                                      "/work/scripts/test_lz4_dictionary_multicall.py", "--inside"],
                                     env=dict(os.environ, RUSTBOX_MULTICALL_TEST_BINARY=str(binary.resolve())))
    observed = json.loads(output)
    if observed != expected_commands(tested, elf_sha) or link.read_bytes() != raw:
        raise ValueError("the LZ4 command results, benchmark or selected release changed")
    return observed


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
    elif args.link and args.binary:
        result = check(args.link, args.binary)
    else:
        p.error("--link and --binary are required")
    print(json.dumps(result, sort_keys=True))
