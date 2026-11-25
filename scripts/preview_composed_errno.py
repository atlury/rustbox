#!/usr/bin/env python3
"""Relink six source-composed errno archives and exercise their public interfaces in the same ELF."""
# SPDX-License-Identifier: 0BSD
import argparse
from functools import partial
import json
from pathlib import Path

from check_cargo_private_inlines import ROOT
from preview_checked_parsers_together import compare
import preview_gawk_ctype as gawk
import preview_gnu_errno as gnu
import preview_ranked_errno as ranked


def run(parent, log, output, pilots):
    inventory = json.loads((ROOT / "evidence/errno-composed-source-counts.json").read_bytes())["packages"]
    if set(pilots) != inventory.keys():
        raise ValueError("select all six source-composed archives")
    packages = {}
    for n in ("grep", "gzip", "sed"):
        packages[n] = (("grep-gzip-sed-composed-errno-archives.json", n), partial(gnu.namespace, n), partial(gnu.commands, n))
    for n, namespace in (("shadow", ranked.shadow_namespace), ("findutils", ranked.findutils_namespace)):
        packages[n] = (n + "-errno-archive.json", namespace, partial(ranked.commands, n, parent.resolve()))
    packages["gawk"] = ("gawk-errno-archive.json", gawk.namespace, gawk.commands)
    for n, pilot in pilots.items():
        verified = json.loads((pilot / "pilot.json").read_bytes())
        for field in ("archive", "compiler_selected_sources", "parent_sources_sha256", "candidate_sources_sha256",
                      "value_reads", "value_writes", "raw_pointer_types_removed"):
            if verified[field] != inventory[n][field]:
                raise ValueError(f"expected composed {n} sources for {field}")
    compare(parent, log, output, pilots, packages)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("parent", "log", "output"):
        p.add_argument(arg, type=Path)
    names = ("grep", "gzip", "sed", "gawk", "shadow", "findutils")
    for name in names:
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    run(a.parent, a.log, a.output, {n: getattr(a, n) for n in names})
