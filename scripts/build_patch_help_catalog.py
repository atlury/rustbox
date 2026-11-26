#!/usr/bin/env python3
"""Replace GNU patch's private sentinel-terminated help pointer array with packed, bounded strings."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from hashlib import sha256
import json
from pathlib import Path

from build_checked_errno import replay
from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import ROOT, digest
from check_e2fsprogs_dirhash_arrays import source_list_digest
from prune_private_inlines import POINTER
from packed_help_catalog import replace_table

MODULE = "src/src/patch.rs"
PARENT = "8dd05bb9400df6c91bde5e300146c56774c42f4b16268afda42f81300fc2362e"
CANONICAL = "ca20b87c33247159560d896283c7ac506f71304bdc3249d9826c8bfb92417106"
MARKER = ".rustbox-patch-help-catalog"


def selection():
    rows = json.loads((ROOT / "evidence/mixed-array-c-string-utilities.json").read_bytes())["identical"]
    key, = [k for k in rows if Path(k).name.startswith("libpatch_")]
    return key, rows[key]


def prepare(link):
    key, row = selection()
    if link["source_library_sha256"].get(key) != row["candidate_sha256"] or key not in link["shared_stdio_layouts"]:
        raise ValueError("expected the checked patch archive and stdio layout")
    current = link.get("native_c_strings", {})
    if current.get(key, row) != row:
        raise ValueError("incompatible prior literal selection")
    link["native_c_strings"] = {**current, key: row}
    return link


def substitute(crate, sources):
    _, row = selection()
    canonical = ROOT / "work/upstream/patch-2.8/src/patch.c"
    original = (crate / MODULE).read_bytes()
    if (digest(canonical) != CANONICAL or sources[MODULE] != PARENT or sha256(original).hexdigest() != PARENT
            or source_list_digest(sources) != row["candidate_sources_sha256"]):
        raise ValueError("GNU patch source or compiler inputs differ")
    data, table = replace_table(original, b"option_help", 66)
    cursor = b"""    let mut p: *const *const ::core::ffi::c_char = ::core::ptr::null::<
        *const ::core::ffi::c_char,
    >();
"""
    loop = br"""        p = &raw const option_help as *const *const ::core::ffi::c_char;
        while !(*p).is_null() {
            Fprintf(stream, b"%s\n\0" as *const u8 as *const ::core::ffi::c_char, *p);
            p = p.offset(1);
        }"""
    bounded = br"""        for line in OPTION_HELP.split_inclusive(|&byte| byte == 0) {
            Fprintf(stream, c"%s\n".as_ptr(), line.as_ptr().cast::<::core::ffi::c_char>());
        }"""
    if data.count(cursor) != 1 or data.count(loop) != 1:
        raise ValueError("GNU patch usage traversal differs")
    data = data.replace(cursor, b"").replace(loop, bounded)
    return {MODULE: data}, dict(canonical_sha256=CANONICAL, module=MODULE, **table,
                                raw_pointer_types_removed=len(POINTER.findall(original))-len(POINTER.findall(data)))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--link", type=Path)
    p.add_argument("--prepare-parent", type=Path)
    p.add_argument("--mounted", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--replay", action="store_true")
    a = p.parse_args()
    if a.mounted:
        compile_mounted_sources(a.mounted, substitute, MARKER, allow_identical=True)
    elif a.prepare_parent:
        print(json.dumps(prepare(json.loads(a.prepare_parent.read_bytes())), indent=2, sort_keys=True))
    elif a.link and a.replay:
        print(json.dumps(replay(a.link, selection()[0], a.output, transform=substitute), indent=2, sort_keys=True))
    elif a.link and a.output:
        stage_selected_archive(a.link, a.output, selection()[0], MARKER, Path(__file__).name)
    else:
        p.error("supply the release and a build destination or --replay")
