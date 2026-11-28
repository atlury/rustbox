#!/usr/bin/env python3
"""Build the same IPRoute2 archive with owned device-group and routing-table lookups."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
from hashlib import sha256
import json
from pathlib import Path

import build_group_names as groups
import build_iproute2_route_tables as tables
from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from cargo_source_parent import cargo_origin, direct_crate

MARKER = ".rustbox-owned-groups-and-tables"


def transform(original):
    routes, route = tables.transform(original)
    both, group = groups.transform(routes)
    grouped, _ = groups.transform(original)
    reversed_order, _ = tables.transform(grouped)
    if both != reversed_order:
        raise ValueError("the two rt_names rewrites overlap")
    return both, dict(route, group_helper_sha256=group["helper_sha256"],
                                candidate_module_sha256=sha256(both).hexdigest(),
                                raw_pointer_types_removed=route["raw_pointer_types_removed"] + group["raw_pointer_types_removed"])


def substitute(crate, sources):
    module, = (name for name in sources if Path(name).name == "rt_names.rs")
    both, facts = transform((crate / module).read_bytes())
    return {module: both}, dict(facts, module=module)


def build(link, archive, output):
    origin = cargo_origin(json.loads(link.read_bytes()), archive)
    if direct_crate(origin) is None:
        stage_selected_archive(link, output, archive, MARKER, Path(__file__).name, linux_scratch=True)
    else:
        from build_group_names_bridge import check_bridge
        from direct_source_pair import build_pair
        check_bridge(link, archive)
        build_pair(link, output, archive, Path(__file__).name, ["--direct", archive], substitute)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--link", type=Path)
    parser.add_argument("--archive")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mounted", type=Path)
    parser.add_argument("--direct")
    args = parser.parse_args()
    if args.mounted:
        compile_mounted_sources(args.mounted, substitute, MARKER, allow_identical=False)
    elif args.direct:
        from build_group_names_bridge import check_bridge
        from direct_source_pair import mounted_pair
        link = Path("/trial/release.json")
        check_bridge(link, args.direct)
        mounted_pair(link, Path("/trial/result"), args.direct, substitute, allow_identical=False)
    elif args.link and args.archive and args.output:
        build(args.link, args.archive, args.output)
    else:
        parser.error("supply --link, --archive and --output")
