#!/usr/bin/env python3
"""Link the verified Shadow and Findutils archives into the complete Linux multicall."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from functools import partial
import json
from pathlib import Path
import subprocess
import sys

from check_cargo_private_inlines import ROOT, digest
from link_rustbox_multicall import coalesce_identical_archive_members, namespace_findutils_inputs, namespace_shadow_library
from preview_checked_parsers_together import compare


def findutils_namespace(archive, residues, release, stage):
    mapped, objects, symbols = namespace_findutils_inputs(archive, residues, stage)
    if symbols != release["findutils_namespaced_symbols"]:
        raise ValueError("Findutils exported symbols differ")
    return mapped, objects


def shadow_namespace(archive, residues, release, stage):
    pins = release["source_library_sha256"]
    key, = [name for name in pins if Path(name).name.startswith("libprocps_ng_") and name.endswith(".a")]
    provider = ROOT / key
    if residues or pins[key] != digest(provider):
        raise ValueError("unexpected Shadow linkage inputs")
    origin, members, _ = coalesce_identical_archive_members(provider, archive, stage / "src/.rustbox-shadow-runtime",
                                                            "Shadow/Procps pinned Rust runtime")
    mapped, symbols = namespace_shadow_library(origin, stage)
    if members != release["shadow_coalesced_runtime_members"] or symbols != release["shadow_namespaced_symbols"]:
        raise ValueError("Shadow runtime members or exported symbols differ")
    return mapped, []


def commands(name, link, elf, stage):
    report = json.loads(subprocess.check_output([sys.executable, "-B", ROOT / "tests/errno-values/command-archives.py",
                                                name, link, "--multicall", elf], cwd=stage))
    if report["binary_sha256"] != digest(elf):
        raise ValueError("tested executable differs")
    expected = json.loads((ROOT / "evidence/errno-ranked-command-baselines.json").read_bytes())[name]["public"]
    for cc in ("gcc", "clang"):
        for mode in ("applet", "subcommand"):
            if report["public"][mode][cc] != expected[cc]:
                raise ValueError(f"incomplete {name} {mode} checks against {cc}")
    return report["public"]


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("parent", "log", "output"):
        p.add_argument(arg, type=Path)
    names = {"shadow": shadow_namespace, "findutils": findutils_namespace}
    for name in names:
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    packages = {name: (name + "-errno-archive.json", namespace, partial(commands, name, a.parent.resolve()))
                for name, namespace in names.items()}
    compare(a.parent, a.log, a.output, {name: getattr(a, name) for name in names}, packages)
