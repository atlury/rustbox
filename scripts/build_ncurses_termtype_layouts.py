#!/usr/bin/env python3
"""Share ncurses' narrow and wide numeric capability layouts within its translated program archive."""
# SPDX-License-Identifier: MIT
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from rank_leaf_c_layouts import STRUCT
from share_stdio_layout import provider_namespace

DEFINITIONS = {
    "termtype": "41e6697aa396d30f041da30c021d4441e087f90441c0baad2c37433e365035bb",
    "termtype2": "c36e97e28f231f2d4363ee09c8341f094db0515716b0069065dd21a8c465e894",
}
MARKER = ".rustbox-ncurses-termtype-layouts"


def substitute(crate, sources, read=None):
    if read is None:
        read = lambda name: (crate / name).read_bytes()
    matches = {name: {} for name in DEFINITIONS}
    for module in sorted(sources):
        data = read(module)
        for declaration in STRUCT.finditer(data):
            name = declaration[1].decode()
            if name in matches and sha256(declaration[0]).hexdigest() == DEFINITIONS[name]:
                if module in matches[name]:
                    raise ValueError("duplicate capability layout in a module")
                matches[name][module] = declaration[0]
    updated, providers, consumers = {}, {}, {}
    for name, copies in matches.items():
        if len(copies) < 2:
            raise ValueError("missing a repeated canonical capability layout: " + name)
        owner = min(copies)
        namespace = provider_namespace(crate / "lib.rs", Path(owner))
        parts = namespace.with_suffix("").parts
        if not all(re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", part) for part in parts):
            raise ValueError("unexpected ncurses provider namespace")
        alias = ("pub use crate::" + "::".join((*parts, name)) + ";").encode()
        providers[name] = owner
        consumers[name] = sorted(copies.keys() - {owner})
        for module in consumers[name]:
            original = copies[module]
            data = updated[module] if module in updated else read(module)
            if data.count(original) != 1 or original.count(b"*mut ") != 9:
                raise ValueError("unexpected terminal type declaration")
            updated[module] = data.replace(original, alias + b"\n" * original.count(b"\n"))
    return updated, dict(providers=providers, reexporting_modules=consumers, declarations_sha256=DEFINITIONS,
                         raw_pointer_types_removed=9 * sum(map(len, consumers.values())))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mounted", type=Path)
    parser.add_argument("--link", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.mounted:
        compile_mounted_sources(args.mounted, substitute, MARKER, allow_identical=True)
    elif args.link and args.output:
        keys = json.loads(args.link.read_bytes())["source_library_sha256"]
        key, = [k for k in keys if k.endswith("/libncurses_6_6_normalized_audit.a")]
        stage_selected_archive(args.link, args.output, key, MARKER, Path(__file__).name)
    else:
        parser.error("--link and --output are required")
