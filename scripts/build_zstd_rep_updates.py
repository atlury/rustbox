#!/usr/bin/env python3
"""Share one safe repeat-offset updater across Zstd's sequence and optimal parsers."""
# SPDX-License-Identifier: BSD-3-Clause OR GPL-2.0-only
import argparse
from hashlib import sha256
from pathlib import Path
import re

from build_zstd_rep_offsets import ARCHIVE, MODULE, substitute as borrow_offsets
from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import ROOT, digest
from prune_private_inlines import POINTER

MARKER = ".rustbox-zstd-repeat-updates"
HEADER = ROOT / "work/upstream/zstd-1.5.7/lib/compress/zstd_compress_internal.h"
DECLARATIONS = {
    "ZSTD_updateRep": "2a46d71f4b708d4df9dc8467a0bbfd8d21370d60330888fd8560914f6ca0e148",
    "ZSTD_newRep": "9abf40379799147bb4eaa0316dc04185bba88fd7aa041f469571b308628f5f6c",
}
UPDATE = b"""#[inline]
pub(crate) fn ZSTD_updateRep(rep: &mut [u32; 3], off_base: u32, ll0: u32) {
    if off_base > 3 {
        *rep = [off_base - 3, rep[0], rep[1]];
    } else {
        let code = off_base.wrapping_sub(1).wrapping_add(ll0);
        if code != 0 {
            let offset = if code == 3 { rep[0].wrapping_sub(1) } else { rep[code as usize] };
            let last = if code >= 2 { rep[1] } else { rep[2] };
            *rep = [offset, rep[0], last];
        }
    }
}"""
NEW = b"""#[inline]
fn ZSTD_newRep(mut rep: [u32; 3], off_base: u32, ll0: u32) -> Repcodes_t {
    ZSTD_updateRep(&mut rep, off_base, ll0);
    repcodes_s { rep }
}"""
IMPORT = b"use crate::src::lib::compress::zstd_compress::ZSTD_updateRep;"
BORROW = re.compile(rb"(ZSTD_updateRep\(\s*)&raw mut ((?:repcodes|rep|updatedRepcodes|\(\*[cd]Repcodes\))\.rep) as \*mut U32,")
COPY = re.compile(rb"(ZSTD_newRep\(\s*)&raw mut (\(\*opt\.offset\((?:prev|prev_0|cur) as isize\)\)\.rep) as \*mut U32\s+as \*const U32,")


def substitute(crate, sources):
    if digest(HEADER) != "ab7754413cef565da559bda7eb738bc2b3708c48877cb9ec37aff767d32c57d1":
        raise ValueError("unexpected canonical repeat-offset implementation")
    changed, previous = borrow_offsets(crate, sources)
    facts = {}
    for module in sorted(sources):
        original = (crate / module).read_bytes()
        data = changed.get(module, original)
        if not any(name.encode() in data for name in DECLARATIONS):
            continue
        consumer = Path(module).stem
        for name, checksum in DECLARATIONS.items():
            pattern = rb'#\[inline\]\nunsafe extern "C" fn ' + name.encode() + rb'\(.*?\n}'
            body, = re.findall(pattern, data, re.S)
            if sha256(body).hexdigest() != checksum:
                raise ValueError("unrecognized private declaration in " + module)
            if name == "ZSTD_updateRep":
                replacement = {"zstd_compress": UPDATE, "zstd_opt": IMPORT,
                               "zstd_compress_superblock": IMPORT}.get(consumer, b"")
            else:
                replacement = NEW if consumer == "zstd_opt" else b""
            data = data.replace(body, replacement + b"\n" * (body.count(b"\n") - replacement.count(b"\n")))
        data, borrows = BORROW.subn(rb"\1&mut \2,", data)
        data, copies = COPY.subn(rb"\1\2,", data)
        expected = {"zstd_compress": (6, 0), "zstd_compress_superblock": (1, 0), "zstd_opt": (0, 3)}.get(consumer, (0, 0))
        if (borrows, copies) != expected:
            raise ValueError("repeat-offset caller differs in " + module)
        changed[module] = data
        facts[module] = dict(raw_pointer_types_removed=len(POINTER.findall(original))-len(POINTER.findall(data)),
                             raw_offsets_removed=original.count(b".offset(")-data.count(b".offset("))
    if len(facts) != 12:
        raise ValueError("expected twelve generated copies of both private helpers")
    return changed, dict(modules=facts, parent_offset_helper_sha256=previous["helper_sha256"],
        canonical_header_sha256=digest(HEADER), shared_update_helper_sha256=sha256(UPDATE).hexdigest(),
        new_rep_helper_sha256=sha256(NEW).hexdigest(),
        raw_pointer_types_removed=sum(x["raw_pointer_types_removed"] for x in facts.values()),
        raw_offsets_removed=sum(x["raw_offsets_removed"] for x in facts.values()))


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
