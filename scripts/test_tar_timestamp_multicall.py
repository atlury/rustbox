#!/usr/bin/env python3
"""Repeat both tar dispatch modes and timestamp Memchecks against the immutable selected ELF."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from check_cargo_private_inlines import ROOT, digest
from preview_tar_timespec import commands
from tar_timespec_archive import selection


def check(link, binary):
    release = json.loads(link.read_bytes())
    record = selection.pinned()
    row = record["pilot"]
    if (release.get(selection.field) != record or release["binary"]["sha256"] != digest(binary)
            or release["source_library_sha256"].get(str(selection.candidate_path(row))) != row["candidate_sha256"]):
        raise ValueError("tar timestamp archive or executable differs from the selected release")
    result = json.loads(subprocess.check_output([ROOT / "scripts/run_multicall_tool.sh", "python3", "-B",
                        "/work/scripts/test_tar_timestamp_multicall.py", "--inside"],
                        env=dict(os.environ, RUSTBOX_MULTICALL_TEST_BINARY=str(binary.resolve()))))
    preview = json.loads((ROOT / "evidence/tar-borrowed-timespec-multicall.json").read_bytes())
    expected = {k: preview[k] for k in ("canonical_cases", "memcheck_runs", "restored_file_and_symlink_mtime_ns",
                                         "command_driver_sha256")}
    if result != dict(expected, multicall_sha256=release["binary"]["sha256"]):
        raise ValueError("tar timestamp results differ from the qualified preview")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--link", type=Path)
    parser.add_argument("--binary", type=Path)
    args = parser.parse_args()
    if args.inside:
        executable = Path(os.environ["RUSTBOX_TEST_ELF"])
        with TemporaryDirectory() as work:
            result = dict(commands(executable, Path(work)), multicall_sha256=digest(executable))
    elif args.link and args.binary:
        result = check(args.link, args.binary)
    else:
        parser.error("--link and --binary are required")
    print(json.dumps(result, sort_keys=True))
