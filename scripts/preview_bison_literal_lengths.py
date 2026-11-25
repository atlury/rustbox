#!/usr/bin/env python3
"""Exercise the Bison length substitutions in both dispatch modes with embedded M4 and skeletons."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import json
from pathlib import Path
import shlex

from check_cargo_private_inlines import ROOT
from link_rustbox_multicall import namespace_bison_inputs
from preview_cargo_multicall import preview
from test_bison_literal_lengths import compare_parsers


def commands(elf, tmp):
    package = ROOT / "work/analysis/bison-3.8.2"
    results = {}
    for mode in ("applet", "subcommand"):
        directory = tmp / mode
        directory.mkdir()
        for name in ("bison", "yacc"):
            executable = directory / name
            if mode == "applet":
                executable.symlink_to(elf)
            else:
                executable.write_text("#!/bin/sh\nexec " + shlex.quote(str(elf)) + " " + name + ' "$@"\n')
                executable.chmod(0o755)
        results[mode] = compare_parsers(directory, package, directory / "bison", directory / "yacc",
                                        embedded=True, bare_name=mode == "subcommand")
    return dict(canonical=results)


def namespace(path, residues, release, stage):
    archive, objects, symbols = namespace_bison_inputs(path, residues, stage)
    if symbols != release["bison_namespaced_symbols"]:
        raise ValueError("Bison link symbols changed")
    return archive, objects


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("parent", "log", "pilot", "output"):
        p.add_argument(arg, type=Path)
    args = p.parse_args()
    qualified = json.loads((ROOT / "evidence/bison-literal-length-pilot.json").read_bytes())
    preview(args.parent, args.log, args.pilot, args.output, qualified, namespace, commands)
