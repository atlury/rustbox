#!/usr/bin/env python3
"""Relink Kmod's unused-type build and compare all seven multicall names against both canonical compilers."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys

from check_cargo_private_inlines import ROOT, digest
from link_rustbox_multicall import namespace_kmod_library
from preview_unused_type_archive import compare_ranked

PROGRAMS = ("kmod", "depmod", "insmod", "lsmod", "modinfo", "modprobe", "rmmod")


def namespaced(path, residues, release, stage):
    mapped, exports = namespace_kmod_library(path, stage)
    if residues or exports != release["kmod_namespaced_symbols"]:
        raise ValueError("Kmod's linked C exports or objects differ from the parent")
    return mapped, []


def commands(elf, stage):
    pins = json.loads((ROOT / "evidence/kmod-34.3-oracle.json").read_bytes())
    modes = {}
    for mode in ("applet", "subcommand"):
        folder = stage / mode
        folder.mkdir()
        for name in PROGRAMS:
            entry = folder / name
            if mode == "applet":
                entry.symlink_to(elf)
            else:
                entry.write_text("#!/bin/sh\nexec " + shlex.quote(str(elf)) + " " + name + ' "$@"\n')
                entry.chmod(0o755)
        for compiler in ("gcc", "clang"):
            oracle = Path("/rustbox-kmod") / ("oracle-" + compiler)
            if any(digest(oracle / name) != pins["binaries"][compiler]["sha256"] for name in PROGRAMS):
                raise ValueError(f"Kmod {compiler} oracle changed")
            out = folder / (compiler + ".json")
            subprocess.run([sys.executable, ROOT / "tests/kmod-oracle-differential.py",
                            "--gcc-root", oracle, "--clang-root", folder, "--output", out], check=True)
            result = json.loads(out.read_bytes())
            if result["passed"] != result["cases"] or result["cases"] != pins["differential"]["cases"]:
                raise ValueError("incomplete Kmod command comparison")
            modes[f"{mode}-{compiler}"] = result["passed"]
    return dict(command_suites=modes)


def run(link, log, source_link, ranking, pilot, output):
    compare_ranked(link, log, source_link, ranking, pilot, output, "kmod-34.3", namespaced, commands)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("link", "log", "source_link", "ranking", "pilot", "output"):
        p.add_argument(name, type=Path)
    args = p.parse_args()
    run(args.link, args.log, args.source_link, args.ranking, args.pilot, args.output)
