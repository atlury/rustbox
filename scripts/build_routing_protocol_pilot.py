#!/usr/bin/env python3
"""Keep IPRoute2 routing protocol names in the checked sparse table with directory overlays."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
from hashlib import sha256
import json
from pathlib import Path

from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import ROOT
from prune_private_inlines import POINTER

MARKER = ".rustbox-routing-protocol-pilot"
# The same canonical table and readers before and after the byte-identical literal pass.
PROFILES = {
    ("b0e522793cee4fdee7cc44beaa3eb0671622540fc0ad395b165d47a6d4c1ca47",
     "771abebc44271401409c19600de2b1bf8114516e4e2f7e27205ee40912a46dda"),
    ("1548771cdc080e0b0c0dfbe9f172056551a655ad197b925aabc4b0c4d70e6793",
     "68e81c051fc350d08d4fddc790551902f58f838510ffd2b268c669ec7fe4618d"),
}


def transform(data):
    start = data.index(b"static mut rtnl_rtprot_tab:")
    table = data[start:data.index(b"\n];\n", start) + 4]
    begin = data.index(b"static mut rtnl_rtprot_init:")
    reverse = data.index(b'pub unsafe extern "C" fn rtnl_rtprot_a2n(', begin)
    readers = data[begin:data.index(b"\n}\n", reverse) + 3]
    if (sha256(table).hexdigest(), sha256(readers).hexdigest()) not in PROFILES:
        raise ValueError("unrecognized routing protocol table or reader functions")
    shared = (ROOT / "compat/iproute2/route_names.rs").read_bytes()
    extended = shared
    for old, new in (
        (b"    vendor: &'static CStr,\n    loaded:", b"    vendor: &'static CStr,\n    directory: Option<&'static CStr>,\n    loaded:"),
        (b"            vendor,\n", b"            vendor,\n            directory: None,\n"),
        (b"                }\n            }\n            slots.map", b"""                }
                if let Some(directory) = self.directory {
                    rtnl_tab_initialize_dir(directory.as_ptr(), slots.as_mut_ptr(), last);
                }
            }
            slots.map"""),
    ):
        if extended.count(old) != 1:
            raise ValueError("unrecognized shared scope/realm reader")
        extended = extended.replace(old, new)
    if data.count(shared) != 1:
        raise ValueError("expected the preceding verified RouteNames implementation")
    replacement = (ROOT / "compat/iproute2/routing_protocols.rs").read_bytes()
    candidate = data.replace(shared, extended).replace(table, b"").replace(readers, replacement)
    if b"rtnl_rtprot_tab" in candidate or b"rtnl_rtprot_init" in candidate:
        raise ValueError("routing protocol state still referenced")
    return candidate, dict(control_module_sha256=sha256(data).hexdigest(), candidate_module_sha256=sha256(candidate).hexdigest(),
                           raw_pointer_types_removed=len(POINTER.findall(data))-len(POINTER.findall(candidate)))


def substitute(crate, sources):
    module, = [m for m in sources if m.endswith("/rt_names.rs")]
    candidate, row = transform((crate / module).read_bytes())
    return {module: candidate}, dict(row, module=module)


def build(link, output, key):
    from cargo_source_parent import cargo_origin, direct_crate
    origin = cargo_origin(json.loads(link.read_bytes()), key)
    if direct_crate(origin) is not None:
        from build_staged_c_strings import build as build_staged
        build_staged(link, output, key, routing_protocols=True)
    else:
        stage_selected_archive(link, output, key, MARKER, Path(__file__).name)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive")
    p.add_argument("--link", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--mounted", type=Path, help=argparse.SUPPRESS)
    args = p.parse_args()
    if args.mounted:
        compile_mounted_sources(args.mounted, substitute, MARKER, allow_identical=False)
    elif args.archive and args.link and args.output:
        build(args.link, args.output, args.archive)
    else:
        p.error("--archive, --link and --output are required")
