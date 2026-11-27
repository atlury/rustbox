#!/usr/bin/env python3
"""Rebuild util-linux isosize with fixed-size borrows for the ISO 9660 numeric fields."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
from hashlib import sha256
from pathlib import Path

from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import ROOT, digest
from prune_private_inlines import POINTER

ARCHIVE = ("work/analysis/util-linux-2.42.4/translations/c2rust-0.22.1/"
           "util-linux-small-02-stable/target/release/libutil_linux_small_02_normalized_reachable.a")
MODULE = "src/disk_utils/isosize.rs"
HEADER = ROOT / "work/upstream/util-linux-2.42.4/include/iso9660.h"
MARKER = ".rustbox-isosize-borrowed-numbers"


def substitute(crate, sources):
    data = (crate / MODULE).read_bytes()
    original = sha256(data).hexdigest()
    if (original != sources[MODULE] or original != "8a8867b4f3b7923245e23f51364da138b9b14e8065fb58f0540097b554839778"
            or digest(HEADER) != "54364409226e5345c5e9bbc525107696710cf06963b867888c35448fa5911d0f"):
        raise ValueError("unrecognized isosize source or canonical ISO numeric fields")
    raw_before = len(POINTER.findall(data))
    offsets_before = data.count(b".offset(")
    for prefix, count, field in (("72", 2, "logical_block_size"), ("73", 4, "volume_space_size")):
        width = 8 * count
        first = data.index(f'#[inline]\nunsafe extern "C" fn isonum_{prefix}1('.encode())
        warning = data.index(b"    if check_match", first)
        little = ", ".join(f"p[{i}]" for i in range(count))
        big = ", ".join(f"p[{i}]" for i in range(count, count * 2))
        body = f"""#[inline]
unsafe fn isonum_{prefix}3(p: &[u8; {2 * count}], check_match: bool) -> u{width} {{
    let le = u{width}::from_le_bytes([{little}]);
    let be = u{width}::from_be_bytes([{big}]);
"""
        data = data[:first] + body.encode() + data[warning:]
        old = f"isonum_{prefix}3(\n                &raw mut {field} as *mut ::core::ffi::c_uchar,".encode()
        if data.count(old) != 1:
            raise ValueError("expected a single owned array at the isosize caller")
        data = data.replace(old, f"isonum_{prefix}3(\n                &{field},".encode())
    facts = dict(module=MODULE, canonical_header_sha256=digest(HEADER), parent_module_sha256=original,
                 candidate_module_sha256=sha256(data).hexdigest(), raw_pointer_types_removed=raw_before-len(POINTER.findall(data)),
                 raw_offsets_removed=offsets_before-data.count(b".offset("), array_borrows=2)
    if facts["raw_pointer_types_removed"] != 8 or facts["raw_offsets_removed"] != 14:
        raise ValueError("unexpected pointer reduction in ISO number readers")
    return {MODULE: data}, facts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--link", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mounted", type=Path)
    args = parser.parse_args()
    if args.mounted:
        compile_mounted_sources(args.mounted, substitute, MARKER, allow_identical=True)
    elif args.link and args.output:
        stage_selected_archive(args.link, args.output.resolve(), ARCHIVE, MARKER, Path(__file__).name)
    else:
        parser.error("supply the parent link report and output directory")
