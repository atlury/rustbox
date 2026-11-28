#!/usr/bin/env python3
"""Relink the unused-type ncurses archive and exercise its programs and configuration helper."""
# SPDX-License-Identifier: 0BSD
import argparse
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

from check_cargo_private_inlines import ROOT, digest
from link_rustbox_multicall import namespace_ncurses_library
from preview_unused_type_archive import compare_ranked


def namespaced(path, residues, release, stage):
    mapped, symbols = namespace_ncurses_library(path, stage)
    if residues or symbols != release["ncurses_namespaced_symbols"]:
        raise ValueError("ncurses exports or C linkage objects differ")
    return mapped, []


def commands(elf, stage):
    pins = json.loads((ROOT / "evidence/ncurses-6.6-oracle.json").read_bytes())
    oracle_root = ROOT / "work/analysis/ncurses-6.6/oracle"
    programs = pins["inventory"]["native_public_names"]
    helper = pins["inventory"]["config_helper"]
    suites = {}
    for mode in ("applet", "subcommand"):
        target = stage / mode
        bindir = target / "usr/bin"
        bindir.mkdir(parents=True)
        share = target / "usr/share"
        share.mkdir()
        shutil.copytree(oracle_root / "gcc-root/usr/share/terminfo", share / "terminfo", symlinks=True)
        for name in [*programs, helper]:
            entry = bindir / name
            if mode == "applet":
                entry.symlink_to(elf)
            else:
                entry.write_text("#!/bin/sh\nexec " + shlex.quote(str(elf)) + " " + name + ' "$@"\n')
                entry.chmod(0o755)
        for compiler in ("gcc", "clang"):
            oracle = oracle_root / (compiler + "-root")
            if any(digest(oracle / "usr/bin" / name) != pins["binaries"][compiler + "-" + name]["sha256"]
                   for name in programs):
                raise ValueError(f"ncurses {compiler} canonical executables changed")
            for suite, script, args, expected in [
                ("commands", "ncurses-oracle-differential.py", ["--gcc-root", oracle, "--clang-root", target],
                 pins["behavior"]["differential"]["cases"]),
                ("config", "ncurses-config-frontend.py", ["--canonical", oracle / "usr/bin" / helper,
                                                          "--native", bindir / helper], 31),
            ]:
                key = f"{mode}-{compiler}-{suite}"
                out = target / (key + ".json")
                subprocess.run([sys.executable, ROOT / "tests" / script, *args, "--output", out], check=True)
                r = json.loads(out.read_bytes())
                if r["passed"] != r["cases"] or r["passed"] != expected:
                    raise ValueError(f"incomplete ncurses {key} suite")
                suites[key] = r["passed"]
    return dict(command_suites=suites)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("link", "log", "source_link", "ranking", "pilot", "output"):
        p.add_argument(name, type=Path)
    a = p.parse_args()
    compare_ranked(a.link, a.log, a.source_link, a.ranking, a.pilot, a.output, "ncurses-6.6", namespaced, commands)
