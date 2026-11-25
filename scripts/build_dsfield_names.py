#!/usr/bin/env python3
"""Replace the IPRoute2 differentiated-services lookup table after the routing protocol reader."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import json
from hashlib import sha256
from pathlib import Path

from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import ROOT, digest
from prune_private_inlines import POINTER

MARKER = ".rustbox-dsfield-names"
CANONICAL = ROOT / "work/upstream/iproute2-7.3.0/lib/rt_names.c"
HELPER = ROOT / "compat/iproute2/dsfield_names.rs"
EXPORT = b'#[no_mangle]\npub unsafe extern "C" fn rtnl_'
PARTS = (
    (b"static mut rtnl_rtdsfield_tab:", EXPORT + b"dsfield_n2a",
     "e737430c561fa81814992a8ac77e22b34b1dc93b84d83582cce368fbfd21a613"),
    (EXPORT + b"dsfield_get_name", EXPORT + b"dscp_n2a",
     "8bbc23a2c667c6cb129b2def6d9a3bf991a33663b6f960362826dcaee7627c35"),
    (EXPORT + b"dsfield_a2n", EXPORT + b"dscp_a2n",
     "b5618687e5ef63553ae8323b0b8f0171861b92f2d599b0e769635c264c42a236"),
)


def transform(source):
    canonical_sha = digest(CANONICAL)
    if canonical_sha != "c7a7fbcfc2995b82fe50b8afd839311e45126e1d3dc135b732988c158f7ec77e":
        raise ValueError("canonical rt_names.c changed")
    helper = HELPER.read_bytes()
    data = source
    # Keep the generated DS field/DSCP formatting and numeric-first DSCP parser.
    # Replace the table, the lookup returning a nullable name and its reverse lookup.
    for index in reversed(range(len(PARTS))):
        first, end, expected = PARTS[index]
        start = source.index(first)
        stop = source.index(end, start)
        if sha256(data[start:stop]).hexdigest() != expected:
            raise ValueError("unexpected generated differentiated-services reader")
        data = data[:start] + (helper if index == 0 else b"") + data[stop:]
    for old, new in (
        (b"fn reverse(&self, query: &CStr)", b"fn reverse(&self, query: &CStr, radix: i32)"),
        (b"strtoul(query.as_ptr(), &mut end, 0)", b"strtoul(query.as_ptr(), &mut end, radix)"),
        (b"self.reverse(CStr::from_ptr(arg))", b"self.reverse(CStr::from_ptr(arg), 0)"),
    ):
        if data.count(old) != 1:
            raise ValueError("shared reverse lookup or its caller changed")
        data = data.replace(old, new)
    if b"rtnl_rtdsfield_tab" in data or b"rtnl_rtdsfield_init" in data:
        raise ValueError("stale DS field table reference")
    return data, dict(control_module_sha256=sha256(source).hexdigest(), candidate_module_sha256=sha256(data).hexdigest(),
                      raw_pointer_types_removed=len(POINTER.findall(source)) - len(POINTER.findall(data)),
                      canonical_sha256=canonical_sha, helper_sha256=sha256(helper).hexdigest())


def substitute(crate, sources):
    module, = [name for name in sources if Path(name).name == "rt_names.rs"]
    data, facts = transform((crate / module).read_bytes())
    return {module: data}, dict(facts, module=module)


def build(link, output, key):
    from cargo_source_parent import cargo_origin, direct_crate
    origin = cargo_origin(json.loads(link.read_bytes()), key)
    if direct_crate(origin) is None:
        stage_selected_archive(link, output, key, MARKER, Path(__file__).name)
    else:
        from build_staged_c_strings import build as build_staged
        build_staged(link, output, key, dsfield=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mounted", type=Path)
    p.add_argument("--link", type=Path)
    p.add_argument("--archive")
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    if args.mounted:
        compile_mounted_sources(args.mounted, substitute, MARKER, allow_identical=False)
    elif args.link and args.archive and args.output:
        build(args.link, args.output.resolve(), args.archive)
    else:
        p.error("--link, --archive and --output are required")
