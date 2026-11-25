#!/usr/bin/env python3
"""Repeat the IPRoute2 comparisons on a saved multicall executable using a Linux-native snapshot."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from check_cargo_private_inlines import ROOT, digest
from preview_routing_protocols import commands


def check(elf, receipt):
    previous = json.loads(receipt.read_bytes())
    expected = previous["candidate"]["sha256"]
    if digest(elf) != expected:
        raise ValueError("the executable differs from the qualified routing protocol preview")
    with TemporaryDirectory() as directory:
        current = commands(elf, Path(directory))
    for key in ("public_names", "differential_driver_sha256", "routel_source_sha256"):
        if current[key] != previous[key]:
            raise ValueError(f"changed canonical input or test coverage: {key}")
    for cc in ("gcc", "clang-18"):
        before, after = previous["canonical"][cc], current["canonical"][cc]
        # Live route output can change between network namespaces. commands()
        # compares each run's status, stdout and stderr with its own oracle.
        for key in ("cases_per_mode", "modes", "canonical_sha256", "filter_status"):
            if before[key] != after[key]:
                raise ValueError(f"changed {cc} comparison or canonical build: {key}")
    return dict(current, elf_sha256=expected)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("elf", type=Path)
    p.add_argument("receipt", type=Path)
    p.add_argument("--mounted", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args()
    if args.mounted:
        print(json.dumps(check(args.elf, args.receipt), indent=2, sort_keys=True))
    else:
        receipt = Path("/work") / args.receipt.resolve().relative_to(ROOT)
        subprocess.run([ROOT / "scripts/run_multicall_tool.sh", "python3", "-B",
                        "/work/scripts/test_routing_protocol_multicall.py", "/rustbox-test-elf/rustbox",
                        receipt, "--mounted"], check=True,
                       env=dict(os.environ, RUSTBOX_MULTICALL_TEST_BINARY=str(args.elf.resolve())))
