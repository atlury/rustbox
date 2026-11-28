#!/usr/bin/env python3
"""Replay shared C layouts through the direct rustc recipes used by the multicall."""
# SPDX-License-Identifier: 0BSD
import argparse
import json
from pathlib import Path

from build_checked_errno import replay
from build_leaf_layout_pilot import select_layouts, substitute
from build_staged_c_strings import build
from cargo_source_parent import cargo_origin, direct_crate
from check_cargo_private_inlines import digest
from verify_c_string_sources import syntax_tool


def run(link, ranking, key, names, output, verify):
    parent = json.loads(link.read_bytes())
    origin = cargo_origin(parent, key)
    if direct_crate(origin) is None:
        raise ValueError("a direct-rustc archive is required")
    selection = select_layouts(link, ranking, key, names)
    if not verify:
        build(link, output, key, leaf_layouts=selection)
        return

    scanner = syntax_tool("leaf-layouts")
    row = replay(link, key, transform=lambda crate, inputs: substitute(crate, inputs, selection, scanner=scanner))
    row.pop("cargo_archive", None)
    row["rustc_archive"] = str(origin)
    row["candidate_sha256"] = digest(output / Path(key).name)
    if row != json.loads((output / "pilot.json").read_bytes()) or row["control_sha256"] != parent["source_library_sha256"][key]:
        raise ValueError("direct compiler receipt differs from independently reconstructed source edits")
    print(json.dumps(row, sort_keys=True))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--link", type=Path, required=True)
    p.add_argument("--ranking", type=Path, required=True)
    p.add_argument("--archive", required=True)
    p.add_argument("--layouts", nargs="+", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--replay", action="store_true")
    args = p.parse_args()
    run(args.link, args.ranking, args.archive, args.layouts, args.output, args.replay)
