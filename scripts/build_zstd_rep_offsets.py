#!/usr/bin/env python3
"""Borrow the three repeat offsets at each private Zstd sequence encoder call."""
# SPDX-License-Identifier: BSD-3-Clause OR GPL-2.0-only
import argparse
from hashlib import sha256
from pathlib import Path

from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import ROOT, digest
from prune_private_inlines import POINTER

ARCHIVE = "work/analysis/zstd-1.5.7/translations/c2rust-0.22.1/zstd-1.5.7-stable/target/release/libzstd_1_5_7_normalized_audit.a"
MODULE = "src/lib/compress/zstd_compress.rs"
CANONICAL = ROOT / "work/upstream/zstd-1.5.7/lib/compress/zstd_compress.c"
MARKER = ".rustbox-zstd-repeat-offsets"
SIGNATURE = b'unsafe extern "C" fn ZSTD_finalizeOffBase('


def substitute(crate, sources):
    data = (crate / MODULE).read_bytes()
    original = sha256(data).hexdigest()
    if (original != sources[MODULE] or original != "811b09ecef9d4c0a77180ecad0d1418e0a34454b8bfaed7ad875b2f6436eaa04"
            or digest(CANONICAL) != "10c315ae609d49b2fc431521aa95908086e69fd917991c5ed9a875af3d1208e8"):
        raise ValueError("unexpected repeat-offset algorithm or compiler input")
    first = data.index(SIGNATURE)
    end = data.index(b"\n}", first) + 2
    helper = data[first:end].replace(SIGNATURE, b"fn ZSTD_finalizeOffBase(").replace(b"mut rep: *const U32", b"rep: &[U32; 3]")
    for index in range(3):
        helper = helper.replace(f"*rep.offset({index} as ::core::ffi::c_int as isize)".encode(), f"rep[{index}]".encode())
    caller = b"&raw mut updatedRepcodes.rep as *mut U32 as *const U32"
    if data.count(caller) != 3 or b"pub struct repcodes_s {\n    pub rep: [U32; 3]," not in data:
        raise ValueError("expected three calls on the owned repeat-offset array")
    candidate = (data[:first] + helper + data[end:]).replace(caller, b"&updatedRepcodes.rep")
    types = len(POINTER.findall(data)) - len(POINTER.findall(candidate))
    offsets = data.count(b".offset(") - candidate.count(b".offset(")
    if types != 7 or offsets != 4 or b"unsafe" in helper or b"*" in helper:
        raise ValueError("unexpected pointer operations in Zstd repeat-offset helper")
    return {MODULE: candidate}, dict(module=MODULE, parent_module_sha256=original,
        candidate_module_sha256=sha256(candidate).hexdigest(), canonical_source_sha256=digest(CANONICAL),
        helper_sha256=sha256(helper).hexdigest(), raw_pointer_types_removed=types,
        raw_offsets_removed=offsets, array_borrows=3)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--link", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--mounted", type=Path)
    args = p.parse_args()
    if args.mounted:
        compile_mounted_sources(args.mounted, substitute, MARKER, allow_identical=True)
    elif args.link and args.output:
        stage_selected_archive(args.link, args.output.resolve(), ARCHIVE, MARKER, Path(__file__).name)
    else:
        p.error("supply --link and --output")
