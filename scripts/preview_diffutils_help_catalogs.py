#!/usr/bin/env python3
"""Run both GNU help catalog conversions together in the complete Linux multicall."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import json
from pathlib import Path
import shlex
import sys

from check_cargo_private_inlines import ROOT
from link_rustbox_multicall import namespace_diffutils_library
from preview_checked_parsers_together import compare
import preview_patch_help_catalog as patch

sys.path.insert(0, str(ROOT / "tests/diffutils-help"))
import catalogs as tests


def namespace(archive, residues, release, stage):
    mapped, symbols = namespace_diffutils_library(archive, stage)
    if residues or symbols != release["diffutils_namespaced_symbols"]:
        raise ValueError("Diffutils public C linkage differs")
    return mapped, []


def patch_commands(elf, stage):
    return patch.commands(elf, stage)["public"]


def commands(elf, stage):
    proof = json.loads((ROOT / "evidence/diffutils-packed-help-archive.json").read_bytes())["results"]
    results = {}
    for mode in ("applet", "subcommand"):
        folder = stage / mode
        folder.mkdir()
        programs = tests.canonical()
        programs["candidate"] = {}
        for name in tests.FIRST_MESSAGE:
            path = folder / name
            if mode == "applet":
                path.symlink_to(elf)
            else:
                path.write_text("#!/bin/sh\nexec " + shlex.quote(str(elf)) + " " + name + ' "$@"\n')
                path.chmod(0o755)
            programs["candidate"][name] = path
        outputs = tests.profiles(programs, folder, subcommand=elf if mode == "subcommand" else None)
        if outputs["profiles"] != proof["public"]["profiles"] or outputs["memcheck_runs"] != 12:
            raise ValueError(f"unexpected translated messages in {mode}")
        if mode == "subcommand":
            # The historical test invokes ./diff and tests the exact diagnostics.
            # Each GNU oracle must see the same bare argv[0] as rustbox diff.
            for cc in ("gcc", "clang"):
                for name, binary in programs[cc].items():
                    path = folder / (name + "-" + cc)
                    path.write_text("#!/bin/bash\nexec -a " + name + " " + shlex.quote(str(binary)) + ' "$@"\n')
                    path.chmod(0o755)
                    programs[cc][name] = path
        files = tests.file_cases(programs, "candidate", folder)
        if files != proof["file_comparisons"]:
            raise ValueError("incomplete Diffutils file comparisons")
        results[mode] = dict(file_cases=files, help_and_error_profiles=outputs["cases"], memcheck_runs=outputs["memcheck_runs"])
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("parent", "log", "output", "patch", "diffutils"):
        p.add_argument(name, type=Path)
    a = p.parse_args()
    packages = {"patch": ("patch-packed-help-archive.json", patch.namespace, patch_commands),
                "diffutils": ("diffutils-packed-help-archive.json", namespace, commands)}
    compare(a.parent, a.log, a.output, {"patch":a.patch, "diffutils":a.diffutils}, packages)
