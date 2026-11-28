#!/usr/bin/env python3
"""Consolidate identical private C variadic function declarations in a selected Cargo archive."""
# SPDX-License-Identifier: 0BSD
import argparse
import json
from pathlib import Path

from build_checked_errno import replay
from build_scalar_ffi import substitute as share
from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from cargo_source_parent import cargo_origin, direct_crate
from check_cargo_private_inlines import ROOT, digest
from verify_c_string_sources import syntax_tool
from direct_source_pair import build_pair, direct_receipt, mounted_pair

SELECTOR = ROOT / "tools/private-inlines/src/bin/variadic-ffi.rs"
MARKER = ".rustbox-variadic-ffi"


def substitute(crate, sources, tool=None):
    changed, facts = share(crate, sources, tool or syntax_tool("variadic-ffi"), all_interfaces=True)
    del facts["all_scalar_interfaces"]
    records = facts.pop("scalar_ffi")
    if not all(", ...)" in row["signature"] for row in records.values()):
        raise ValueError("expected C variadic declarations with an exact fixed prefix")
    return changed, dict(facts, variadic_ffi=records, variadic_scanner_sha256=digest(SELECTOR))


def replay_layer(parent, read_parent, row, tool):
    from build_scalar_ffi import replay_layer as replay_declarations
    return replay_declarations(parent, read_parent, row, tool, transform=substitute)


def build(link, key, output):
    if direct_crate(cargo_origin(json.loads(link.read_bytes()), key)) is not None:
        return build_pair(link, output, key, Path(__file__).name, ["--mounted-direct", key], substitute)
    stage_selected_archive(link, output, key, MARKER, Path(__file__).name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mounted", type=Path)
    parser.add_argument("--mounted-direct")
    parser.add_argument("--link", type=Path)
    parser.add_argument("--archive")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    if args.mounted_direct:
        mounted_pair(Path("/trial/release.json"), Path("/trial/result"), args.mounted_direct, substitute, allow_identical=True)
    elif args.mounted:
        compile_mounted_sources(args.mounted, substitute, MARKER, allow_identical=True)
    elif args.link and args.archive and args.output:
        if args.replay:
            if direct_crate(cargo_origin(json.loads(args.link.read_bytes()), args.archive)) is not None:
                row = direct_receipt(args.link, args.archive, substitute)
                row["candidate_sha256"] = digest(args.output / Path(args.archive).name)
                if row != json.loads((args.output / "pilot.json").read_bytes()):
                    raise ValueError("direct compiler receipt differs from the independent replay")
            else:
                row = replay(args.link, args.archive, args.output, transform=substitute)
            print(json.dumps(row, sort_keys=True))
        else:
            build(args.link, args.archive, args.output)
    else:
        parser.error("supply --link, --archive and --output")
