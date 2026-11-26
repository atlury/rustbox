#!/usr/bin/env python3
"""Replace IPRoute2's private terminal escape pointer table and mutable palettes with bounded byte rows."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path

from build_checked_errno import replay
from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import ROOT, digest
from prune_private_inlines import POINTER

PALETTE = ROOT / "compat/iproute2/color_palette.rs"
CFILE = ROOT / "work/upstream/iproute2-7.3.0/lib/color.c"
MARKER = ".rustbox-iproute2-color-palette"
NATIVE_TABLE = "5491b592cecf2fe30c4dd4e268f44a43a32febc080d5383ce3a66205696c3e97"
PREFIX = b"""color_codes[(if is_dark_bg != 0 {
                    attr_colors_dark[attr as usize] as ::core::ffi::c_uint
                } else {
                    attr_colors_light[attr as usize] as ::core::ffi::c_uint
                }) as usize]"""
SUFFIX = b"color_codes[C_CLEAR as ::core::ffi::c_int as usize]"


def substitute(crate, sources):
    module, = [m for m in sources if m.endswith("/lib/color.rs")]
    data = (crate / module).read_bytes()
    begin = data.index(b"static mut color_codes:")
    end = data.index(b"\n];\n", data.index(b"static mut attr_colors_dark:", begin)) + 4
    table = data[begin:end]
    if (digest(CFILE) != "e898b99edd5a1915fd213d162ffc4d5c05e6cddd87c2b1b94e9e392e0db07889"
            or sha256(table).hexdigest() != NATIVE_TABLE or data.count(PREFIX) != 1 or data.count(SUFFIX) != 1
            or data.count(b"color_codes") != 3 or any(data.count(n) != 2 for n in (b"attr_colors_dark", b"attr_colors_light"))
            or sources[module] != sha256(data).hexdigest()):
        raise ValueError("unrecognized IPRoute2 terminal color tables or consumers")
    new = data[:begin] + PALETTE.read_bytes() + data[end:]
    new = new.replace(PREFIX,b"rustbox_color_escape(is_dark_bg != 0, attr as usize).as_ptr().cast::<::core::ffi::c_char>()")
    new = new.replace(SUFFIX,b"RUSTBOX_CLEAR_COLOR.as_ptr().cast::<::core::ffi::c_char>()")
    return {module:new}, dict(module=module, canonical_sha256=digest(CFILE), helper_sha256=digest(PALETTE),
                              parent_module_sha256=sources[module], candidate_module_sha256=sha256(new).hexdigest(),
                              static_pointer_slots_removed=16, mutable_tables_removed=3,
                              raw_pointer_types_removed=len(POINTER.findall(data))-len(POINTER.findall(new)))


def replay_all(link):
    from link_rustbox_multicall import IPROUTE2_PROGRAMS
    raw = link.read_bytes()
    selected = json.loads(raw)["source_library_sha256"]
    keys = sorted(k for k in selected if k.startswith("work/analysis/iproute2-7.3.0/") and k.endswith(".a"))
    if {Path(k).name for k in keys} != {"lib" + n + "_audit.a" for n in IPROUTE2_PROGRAMS} or len(keys) != len(IPROUTE2_PROGRAMS):
        raise ValueError("expected exactly one archive per IPRoute2 engine")
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = dict(zip(keys,pool.map(lambda k: replay(link,k,transform=substitute),keys)))
    if link.read_bytes() != raw:
        raise ValueError("parent selection changed during the source replay")
    return dict(link_report_sha256=sha256(raw).hexdigest(),engines=results,
                static_pointer_slots_removed=sum(r["static_pointer_slots_removed"] for r in results.values()),
                mutable_tables_removed=sum(r["mutable_tables_removed"] for r in results.values()),
                raw_pointer_types_removed=sum(r["raw_pointer_types_removed"] for r in results.values()))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--link",type=Path)
    p.add_argument("--archive")
    p.add_argument("--output",type=Path)
    p.add_argument("--mounted",type=Path)
    p.add_argument("--replay",action="store_true")
    p.add_argument("--all-replay",action="store_true")
    a = p.parse_args()
    if a.mounted:
        compile_mounted_sources(a.mounted, substitute, MARKER, allow_identical=True)
    elif a.link and a.all_replay:
        print(json.dumps(replay_all(a.link),indent=2,sort_keys=True))
    elif a.link and a.archive and a.replay:
        print(json.dumps(replay(a.link,a.archive,a.output,transform=substitute),indent=2,sort_keys=True))
    elif a.link and a.archive and a.output:
        stage_selected_archive(a.link,a.output,a.archive,MARKER,Path(__file__).name)
    else:
        p.error("supply the target archive and its link report")
