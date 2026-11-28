#!/usr/bin/env python3
"""Replace IPRoute2's routing-table hash and its C ABI lookups on selected compiler inputs."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import json
from hashlib import sha256
from pathlib import Path

from build_dsfield_names import CANONICAL
from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from cargo_source_parent import cargo_origin, direct_crate
from check_cargo_private_inlines import ROOT, digest
from prune_private_inlines import POINTER

HELPER = ROOT / "compat/iproute2/route_tables.rs"
MARKER = ".rustbox-owned-route-tables"


def transform(source):
    canonical = digest(CANONICAL)
    if canonical != "c7a7fbcfc2995b82fe50b8afd839311e45126e1d3dc135b732988c158f7ec77e":
        raise ValueError("canonical route table code changed")
    start = source.index(b"static mut dflt_table_entry:")
    last = source.index(b'pub unsafe extern "C" fn rtnl_rttable_a2n(', start)
    stop = source.index(b"\n}\n", last) + 3
    if sha256(source[start:stop]).hexdigest() != "e083f917749eb345d4f2377b1174398574b60a3fb80d92bb69c44397e8acaa10":
        raise ValueError("unrecognized generated routing-table definitions")
    helper = HELPER.read_bytes()
    candidate = source[:start] + helper + source[stop:]
    if b"rtnl_rttable_hash" in candidate or b"dflt_table_entry" in candidate:
        raise ValueError("old routing-table hash still referenced")
    return candidate, dict(control_module_sha256=sha256(source).hexdigest(), candidate_module_sha256=sha256(candidate).hexdigest(),
        canonical_sha256=canonical, helper_sha256=sha256(helper).hexdigest(),
        raw_pointer_types_removed=len(POINTER.findall(source)) - len(POINTER.findall(candidate)))


def substitute(crate, sources):
    module, = [m for m in sources if Path(m).name == "rt_names.rs"]
    data, facts = transform((crate / module).read_bytes())
    return {module: data}, dict(facts, module=module)


def build(link, output, archive, *, linux_scratch=False):
    origin = cargo_origin(json.loads(link.read_bytes()), archive)
    if direct_crate(origin) is None:
        stage_selected_archive(link, output, archive, MARKER, Path(__file__).name, linux_scratch=linux_scratch)
    else:
        from build_group_names_bridge import check_bridge
        from direct_source_pair import build_pair
        check_bridge(link, archive)
        build_pair(link, output, archive, Path(__file__).name, ["--direct", archive], substitute)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mounted", type=Path)
    p.add_argument("--direct", help=argparse.SUPPRESS)
    p.add_argument("--link", type=Path)
    p.add_argument("--archive")
    p.add_argument("--output", type=Path)
    p.add_argument("--linux-scratch", action="store_true", help="keep intermediate Cargo files in disposable Linux volumes")
    args = p.parse_args()
    if args.direct:
        from build_group_names_bridge import check_bridge
        from direct_source_pair import mounted_pair
        link = Path("/trial/release.json")
        check_bridge(link, args.direct)
        mounted_pair(link, Path("/trial/result"), args.direct, substitute, allow_identical=False)
    elif args.mounted:
        compile_mounted_sources(args.mounted, substitute, MARKER, allow_identical=False)
    elif args.link and args.archive and args.output:
        build(args.link, args.output, args.archive, linux_scratch=args.linux_scratch)
    else:
        p.error("supply a Cargo archive, release link and output directory")
