#!/usr/bin/env python3
"""Relink the complete selected multicall in isolation and exercise the borrowed GNU tar timestamps."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess

from build_tar_timespec_pilot import ARCHIVE
from check_cargo_private_inlines import ROOT, digest
from link_rustbox_multicall import namespace_tar_inputs
from preview_cargo_multicall import preview as preview_archive

def commands(elf, tmp):
    driver = ROOT / "tests/tar-oracle-differential.py"
    canonical = ROOT / "work/analysis/tar-1.35/oracle"
    cases = {}
    for mode in ("applet", "subcommand"):
        stage = tmp / mode
        for utility, path in (("tar", "usr/bin/tar"), ("rmt", "usr/libexec/rmt")):
            entry = stage / path
            entry.parent.mkdir(parents=True, exist_ok=True)
            if mode == "applet":
                entry.symlink_to(elf)
            else:
                entry.write_text("#!/bin/sh\nexec " + shlex.quote(str(elf)) + " " + utility + ' "$@"\n')
                entry.chmod(0o755)
        for compiler in ("gcc", "clang"):
            result = tmp / f"{mode}-{compiler}.json"
            subprocess.run(["python3", driver, "--gcc-root", canonical / (compiler + "-root"), "--clang-root", stage,
                            "--output", result], check=True, stdout=subprocess.DEVNULL)
            row = json.loads(result.read_bytes())
            if row["cases"] != 18 or row["passed"] != row["cases"]:
                raise ValueError("tar/rmt public dispatch differs from its canonical build")
            cases[f"{mode}-{compiler}"] = row["passed"]
    src, dest = tmp / "source", tmp / "extracted"
    src.mkdir()
    dest.mkdir()
    (src / "data").write_bytes(b"tar timestamp probe\n")
    (src / "link").symlink_to("data")
    stamp = 1710000000123456789
    for child in src.iterdir():
        os.utime(child, ns=(stamp, stamp), follow_symlinks=False)
    archive = tmp / "timestamps.tar"
    for i, args in enumerate((["-c", "--format=pax", "-f", archive, "-C", src, "data", "link"],
                              ["-xf", archive, "-C", dest])):
        report = tmp / f"valgrind-{i}.log"
        subprocess.run(["valgrind", "--leak-check=full", "--errors-for-leak-kinds=definite,indirect,possible",
                        "--error-exitcode=99", "--log-file=" + str(report), elf, "tar", *args], check=True)
        if "ERROR SUMMARY: 0 errors" not in report.read_text():
            raise ValueError("tar multicall Memcheck failed")
    if ((dest / "data").read_bytes() != (src / "data").read_bytes() or os.readlink(dest / "link") != "data"
            or any(p.lstat().st_mtime_ns != stamp for p in dest.iterdir())):
        raise ValueError("multicall extraction lost the file, symlink or nanosecond timestamps")
    return dict(canonical_cases=cases, memcheck_runs=2, restored_file_and_symlink_mtime_ns=stamp,
                command_driver_sha256=digest(driver))


def preview(parent, log, pilot, output):
    qualified = json.loads((ROOT / "evidence/tar-borrowed-timespec-pilot.json").read_bytes())
    if qualified["archive"] != ARCHIVE:
        raise ValueError("unexpected tar archive")

    def namespace(path, residues, release, stage):
        archive, objs, symbols, imports = namespace_tar_inputs(path, residues, release["acl_namespaced_symbols"], stage)
        if symbols != release["tar_namespaced_symbols"] or imports != release["tar_acl_imports"]:
            raise ValueError("tar symbol names or ACL imports changed")
        return archive, objs

    preview_archive(parent, log, pilot, output, qualified, namespace, commands)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("parent_link", "parent_build_log", "pilot", "new_directory"):
        parser.add_argument(arg, type=Path)
    args = parser.parse_args()
    preview(args.parent_link, args.parent_build_log, args.pilot, args.new_directory)
