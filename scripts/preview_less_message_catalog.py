#!/usr/bin/env python3
"""Relink the checked Less catalog and exercise help overrides using both applet entry paths."""
# SPDX-License-Identifier: BSD-2-Clause OR GPL-3.0-or-later
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shlex
import subprocess

from check_cargo_private_inlines import ROOT, digest
from link_rustbox_multicall import namespace_less_library
from preview_cargo_multicall import preview


def namespaced(path, residues, release, stage):
    mapped, symbols = namespace_less_library(path, stage)
    if residues or symbols != release["less_namespaced_symbols"]:
        raise ValueError("Less object closure or C exports differ")
    return mapped, []


def commands(elf, work):
    oracle = ROOT / "work/analysis/less-710/oracle"
    pins = json.loads((ROOT / "evidence/less-710-oracle.json").read_bytes())["binaries"]
    executables = {}
    for cc in ("gcc", "clang"):
        directory = oracle / cc
        if any(digest(directory / name) != pins[cc][name]["sha256"] for name in ("less", "lessecho")):
            raise ValueError("unexpected canonical Less executable")
        executables[cc] = directory / "less"
    suites = {}
    for mode in ("applet", "subcommand"):
        directory = work / mode
        directory.mkdir()
        for name in ("less", "lessecho"):
            path = directory / name
            if mode == "applet":
                path.symlink_to(elf)
            else:
                path.write_text("#!/bin/sh\nexec " + shlex.quote(str(elf)) + " " + name + ' "$@"\n')
                path.chmod(0o755)
        executables[mode] = directory / "less"
        for cc in ("gcc", "clang"):
            report = directory / (cc + ".json")
            subprocess.run(["python3", ROOT / "tests/less-oracle-differential.py", "--gcc-directory", oracle / cc,
                            "--clang-directory", directory, "--output", report], check=True, stdout=subprocess.DEVNULL)
            data = json.loads(report.read_bytes())
            if data["cases"] != data["passed"] or not data["passed"]:
                raise ValueError("incomplete Less command differential")
            suites[mode + "-" + cc] = data["passed"]
    cases = [(b"HELP catalog-test\\nline2\n", b"catalog-test\nline2"), (b"HELP first\nHELP second\n", b"second"),
             (b"HELP \xffraw\n", b"\xffraw"), (b"HELP help\\000discard\n", b"help" + bytes(8))]
    profiles = []
    for contents, expected in cases:
        path = work / "messages"
        path.write_bytes(contents)
        for target in executables.values():
            run = subprocess.run([target, "--help"], stdin=subprocess.DEVNULL, capture_output=True, timeout=30,
                                 env=dict(os.environ, HOME=str(work), LC_ALL="C", LESS="", LESSMSG=str(path)))
            if run.returncode or run.stderr or run.stdout != expected:
                raise ValueError((target.name, contents, run.returncode, run.stderr[:120], run.stdout[:120]))
        profiles.append(sha256(expected).hexdigest())
    return dict(command_suites=suites, help_commands=len(cases)*len(executables), help_output_sha256=profiles)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("parent", "log", "pilot", "output"):
        p.add_argument(arg, type=Path)
    a = p.parse_args()
    checked = json.loads((ROOT / "evidence/less-checked-message-catalog.json").read_bytes())["archive"]
    preview(a.parent, a.log, a.pilot, a.output, checked, namespaced, commands)
