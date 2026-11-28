#!/usr/bin/env python3
"""Replace GNU tar's two private sentinel-terminated pattern tables on compiler-selected sources."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

from build_checked_errno import replay
from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import ROOT, digest
from prune_private_inlines import POINTER

CANONICAL = ROOT / "work/upstream/tar-1.35/src/names.c"
MARKER = ".rustbox-exclusion-tables"
TABLES = ("vcs_file_table", "backup_file_table")
MODULE = "src/src/names.rs"


def canonical_patterns():
    source = CANONICAL.read_bytes()
    if sha256(source).hexdigest() != "b1b4ebf14cdc82f27aa7265ca59ae5c7df2d54fe311a350484b175921396fb96":
        raise ValueError("unexpected GNU tar names.c")
    result = {}
    for name in TABLES:
        start = ("static char const * const " + name + "[] = {").encode()
        block = source.split(start, 1)[1].split(b"};", 1)[0]
        block = re.sub(rb"/\*.*?\*/", b"", block, flags=re.S)
        pattern = rb'"([A-Za-z0-9.#*~={}_-]+)"'
        if not re.fullmatch(rb"\s*(?:" + pattern + rb"\s*,\s*)+NULL\s*", block):
            raise ValueError(f"unsupported canonical pattern in {name}")
        result[name] = re.findall(pattern, block)
    return result


def substitute(crate, sources):
    source = (crate / MODULE).read_bytes()
    start = source.index(b"static mut vcs_file_table:")
    end = source.index(b'unsafe extern "C" fn handle_file_selection_option(', start)
    if sha256(source[start:end]).hexdigest() != "d3df038db464272850728a60631dd1a3cd65476a4b5a3e47bde0c924e62199bd":
        raise ValueError("translated GNU tar exclusion tables or loop changed")
    patterns = canonical_patterns()
    constants = []
    tail = source[end:]
    for name, entries in patterns.items():
        constant = name.upper()
        packed = b"".join(entry + rb"\0" for entry in entries)
        constants.append(b"const " + constant.encode() + b': &[u8] = b"' + packed + b'";\n')
        arg = ("&raw const " + name + " as *const *const ::core::ffi::c_char").encode()
        if tail.count(arg) != 1 or source.count(name.encode()) != 2:
            raise ValueError(f"unexpected use of {name}")
        tail = tail.replace(arg, constant.encode())
    if source.count(b"add_exclude_array") != 3:
        raise ValueError("unexpected tar table iterator users")
    helper = b"""
fn add_exclude_array(names: &'static [u8], options: ::core::ffi::c_int) {
    for bytes in names.split_inclusive(|byte| *byte == 0) {
        let name = ::core::ffi::CStr::from_bytes_with_nul(bytes).expect("terminated tar exclusion");
        // GNU add_exclude can retain this pattern; its backing storage is static.
        unsafe { add_exclude(excluded, name.as_ptr(), options); }
    }
}
"""
    changed = source[:start] + b"".join(constants) + helper + tail
    return {MODULE:changed}, dict(module=MODULE, canonical_source_sha256=digest(CANONICAL),
        patterns={k:[x.decode("ascii") for x in v] for k,v in patterns.items()},
        control_module_sha256=sha256(source).hexdigest(), candidate_module_sha256=sha256(changed).hexdigest(),
        raw_pointer_types_removed=len(POINTER.findall(source))-len(POINTER.findall(changed)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mounted", type=Path)
    parser.add_argument("--link", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    if args.mounted:
        compile_mounted_sources(args.mounted, substitute, MARKER, allow_identical=False)
    elif args.link and args.output:
        release = json.loads(args.link.read_bytes())
        key, = [k for k in release["source_library_sha256"] if Path(k).name == "libtar_1_35_normalized_audit.a"]
        if args.replay:
            print(json.dumps(replay(args.link, key, args.output, transform=substitute),sort_keys=True))
        else:
            stage_selected_archive(args.link, args.output, key, MARKER, Path(__file__).name)
    else:
        parser.error("supply --link and --output")
