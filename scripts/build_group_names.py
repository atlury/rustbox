#!/usr/bin/env python3
"""Replace the IPRoute2 device-group linked lists in a compiler-selected rt_names module."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
from hashlib import sha256
import json
from pathlib import Path

from build_checked_errno import replay
from build_dsfield_names import CANONICAL
from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import ROOT, digest
from prune_private_inlines import POINTER

MARKER = ".rustbox-device-group-names"
HELPER = ROOT / "compat/iproute2/group_names.rs"


def transform(source):
    start = b"static mut dflt_group_entry:"
    stop = b"// SPDX-License-Identifier: GPL-2.0-or-later\nstatic NETLINK_PROTOCOLS:"
    if (source.count(start) != 1 or source.count(stop) != 1
            or digest(CANONICAL) != "c7a7fbcfc2995b82fe50b8afd839311e45126e1d3dc135b732988c158f7ec77e"):
        raise ValueError("unexpected IPRoute2 group-name source or canonical input")
    a, b = source.index(start), source.index(stop)
    if sha256(source[a:b]).hexdigest() != "b21b3650d62d00633e7c94d836b8cdccbcc6943ee9025eb722cd81dd439fce30":
        raise ValueError("generated group-name functions differ from their qualified inputs")
    helper = HELPER.read_bytes()
    result = source[:a] + helper + source[b:]
    if any(name in result for name in (b"rtnl_group_hash", b"dflt_group_entry", b"rtnl_group_initialize")):
        raise ValueError("a generated group-name table reference remains")
    return result, dict(control_module_sha256=sha256(source).hexdigest(), candidate_module_sha256=sha256(result).hexdigest(),
                        canonical_sha256=digest(CANONICAL), helper_sha256=sha256(helper).hexdigest(),
                        raw_pointer_types_removed=len(POINTER.findall(source)) - len(POINTER.findall(result)))


def substitute(crate, sources):
    module, = [name for name in sources if Path(name).name == "rt_names.rs"]
    data, facts = transform((crate / module).read_bytes())
    return {module:data}, dict(facts, module=module)


def build(link, output, key):
    stage_selected_archive(link, output, key, MARKER, Path(__file__).name)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mounted", type=Path)
    p.add_argument("--link", type=Path)
    p.add_argument("--archive")
    p.add_argument("--output", type=Path)
    p.add_argument("--replay", action="store_true")
    args = p.parse_args()
    if args.mounted:
        compile_mounted_sources(args.mounted, substitute, MARKER, allow_identical=False)
    elif args.link and args.archive and args.output:
        if args.replay:
            print(json.dumps(replay(args.link, args.archive, args.output, transform=substitute), sort_keys=True))
        else:
            build(args.link, args.output, args.archive)
    else:
        p.error("supply a saved link, Cargo archive and output directory")
