#!/usr/bin/env python3
"""Link both owned IPRoute2 readers together and compare device-group and DS field CLI behavior."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
from hashlib import sha256
import json
from pathlib import Path

from check_cargo_private_inlines import ROOT, digest
from link_rustbox_multicall import IPROUTE2_PROGRAMS
from preview_cargo_multicall import preview_link
from preview_routing_protocols import dsfield_commands, group_commands, qualified_engines
from stage_dsfield_archives import FIELD, candidate_path, parent_view
from test_group_names import configure


def combined_commands(elf, stage):
    group = group_commands(elf, stage)
    # The group comparison verified both private tmpfs mounts before populating them.
    configure("empty", Path("/etc/iproute2/group"), Path("/usr/share/iproute2/group"))
    return dsfield_commands(elf, stage, checked=group)


def preview(parent, log, batch, output):
    raw = parent.read_bytes()
    release = json.loads(raw)
    parent_view(release)
    proof = ROOT / "evidence/iproute2-combined-name-tables-archives.json"
    qualified = json.loads(proof.read_bytes())
    if (qualified != json.loads((batch / "combined-results.json").read_bytes())
            or qualified["link_sha256"] != sha256(raw).hexdigest() or qualified["binary_sha256"] != release["binary"]["sha256"]):
        raise ValueError("the combined archive tests belong to a different release")
    origins = {str(candidate_path(row)): row for row in release[FIELD].values()}
    def resolve(name, key, expected):
        item = qualified["verified"][key]
        folder = batch / Path(key).stem
        row = json.loads((folder / "pilot.json").read_bytes())
        if (item != json.loads((folder / "combined-comparison.json").read_bytes()) or item["archive"] != row
                or item["link_sha256"] != qualified["link_sha256"] or row["archive"] != key
                or row["control_sha256"] != origins[key]["candidate_sha256"] or expected != row["control_sha256"]
                or row["parent_sources_sha256"] != origins[key]["candidate_sources_sha256"]
                or row["control_binary_sha256"] != release["binary"]["sha256"]):
            raise ValueError(f"combined source or compiler receipt changed for {name}")
        return folder / Path(key).name, row["candidate_sha256"]
    prepare = qualified_engines(release, qualified["verified"], IPROUTE2_PROGRAMS, resolve)
    def exercise(elf, stage):
        return dict(combined_commands(elf, stage), canonical_archives_sha256=digest(proof))
    preview_link(parent, raw, log, output, prepare, exercise)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("parent", "log", "batch", "output"):
        parser.add_argument(arg, type=Path)
    args = parser.parse_args()
    preview(args.parent, args.log, args.batch, args.output)
