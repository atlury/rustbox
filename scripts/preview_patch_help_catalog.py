#!/usr/bin/env python3
"""Check GNU patch's packed help in the full executable through both public dispatch paths."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import json
from pathlib import Path
import shlex
import sys

from check_cargo_private_inlines import ROOT
from link_rustbox_multicall import namespace_patch_library
from preview_cargo_multicall import preview

sys.path.insert(0, str(ROOT / "tests/patch-help"))
from compare import canonical_programs, compare


def namespace(archive, residues, release, stage):
    mapped, symbols = namespace_patch_library(archive, stage)
    if residues or symbols != release["patch_namespaced_symbols"]:
        raise ValueError("patch C linkage differs from the release")
    return mapped, []


def commands(elf, stage):
    proof = json.loads((ROOT / "evidence/patch-packed-help-archive.json").read_bytes())
    results = {}
    for mode in ("applet", "subcommand"):
        work = stage / mode
        work.mkdir()
        patch = work / "patch"
        if mode == "applet":
            patch.symlink_to(elf)
            invocation = [patch]
        else:
            patch.write_text("#!/bin/sh\nexec " + shlex.quote(str(elf)) + ' patch "$@"\n')
            patch.chmod(0o755)
            invocation = [elf, "patch"]
        result = compare(dict(canonical_programs(), candidate=patch), work, proof["archive"],
                         memcheck_command=invocation, argv_zero="patch" if mode == "subcommand" else "./patch")
        if any(result[k] != v for k, v in proof["public"].items() if k != "memcheck_runs") or result["memcheck_runs"] != 3:
            raise ValueError(f"GNU patch {mode} differs from standalone commands")
        results[mode] = result
    return dict(public=results)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("parent", "log", "pilot", "output"):
        p.add_argument(name, type=Path)
    a = p.parse_args()
    proof = json.loads((ROOT / "evidence/patch-packed-help-archive.json").read_bytes())
    preview(a.parent, a.log, a.pilot, a.output, proof["archive"], namespace, commands)
