#!/usr/bin/env python3
"""Move GNU tar's private argmatch name tables into immutable Rust C-string references."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import json
from pathlib import Path
import re

from build_checked_errno import replay
from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import ROOT, digest
from prune_private_inlines import POINTER

CANONICAL = ROOT / "work/upstream/tar-1.35"
MARKER = ".rustbox-tar-argmatch-tables"
TABLES = {
    "src/src/warning.rs": ("src/warning.c", ("warning_args",)),
    "src/src/tar.rs": ("src/tar.c", ("atime_preserve_args", "hole_detection_args", "sort_mode_arg")),
    "src/gnu/backup_find.rs": ("gnu/backup-find.c", ("backup_args",)),
}
HASHES = {
    "src/warning.c": "3de8461f8b18f84b082a53f71e12ba2f899880ea88aa6b99b6ddbfd625841e47",
    "src/tar.c": "cc5fad63d3ae5b7610cb3a30a670edb2e27baacd2d7668703e464a69577c86d5",
    "gnu/backup-find.c": "b9b4f9f3871a45f5b8bbcdd7e604ee89cb05d3c1be47850cd63673a3f9ca50e5",
    "gnu/argmatch.c": "7e24c3717c38f2cfbdd55642849b7f9659d94e2eb64544fa195017d5fdd3aef7",
}


def options(source, table):
    name = table.encode()
    block, = re.findall(rb"static char const \*const " + name + rb"\[\] =\s*\{(.*?)\};", source, re.S)
    block = re.sub(rb"/\*.*?\*/", b"", block, flags=re.S)
    if table == "sort_mode_arg":
        # Confirm the Linux configuration against the actual translated table below.
        block = block.replace(b'#if D_INO_IN_DIRENT\n  "inode",\n#endif', b'"inode",')
    if not re.fullmatch(rb'\s*(?:"[a-z-]+"\s*,\s*)+NULL\s*', block):
        raise ValueError(f"unsupported canonical option table {table}")
    return re.findall(rb'"([a-z-]+)"', block)


def replace(source, table, names):
    name = table.encode()
    count = str(len(names) + 1).encode()
    old = (b"static mut " + name + b": [*const ::core::ffi::c_char; " + count + b"] = [\n"
           + b"".join(b'    b"' + option + b'\\0" as *const u8 as *const ::core::ffi::c_char,\n' for option in names)
           + b"    ::core::ptr::null::<::core::ffi::c_char>(),\n];")
    addr = b"&raw const " + name + b" as *const *const ::core::ffi::c_char"
    # __xargmatch_internal consumes the array synchronously and returns an index.
    call = rb"__xargmatch_internal\(\s*[^,;()]+,\s*(?:arg|version),\s*" + re.escape(addr) + rb","
    if (source.count(old) != 1 or len(re.findall(rb"\b" + name + rb"\b", source)) != 2
            or len(re.findall(call, source)) != 1):
        raise ValueError(f"canonical options or the sole argmatch call site differ for {table}")
    const_name = name.upper()
    new = (b"const " + const_name + b": [Option<&::core::ffi::CStr>; " + count + b"] = [\n"
           + b"".join(b'    Some(c"' + option + b'"),\n' for option in names) + b"    None,\n];")
    # This temporary lasts through the whole call. The names have static storage.
    view = const_name + b".map(|s| s.map_or(::core::ptr::null(), ::core::ffi::CStr::as_ptr)).as_ptr()"
    return source.replace(old, new).replace(addr, view)


def substitute(crate, sources):
    if not TABLES.keys() <= sources.keys() or any(digest(CANONICAL / k) != v for k, v in HASHES.items()):
        raise ValueError("canonical tar matcher or selected modules differ")
    changed, entries = {}, {}
    removed = 0
    for module, (canonical, tables) in TABLES.items():
        old = (crate / module).read_bytes()
        data = old
        source = (CANONICAL / canonical).read_bytes()
        for table in tables:
            names = options(source, table)
            data = replace(data, table, names)
            entries[table] = [name.decode("ascii") for name in names]
        changed[module] = data
        removed += len(POINTER.findall(old)) - len(POINTER.findall(data))
    return changed, dict(argmatch_tables=entries, canonical_source_sha256=HASHES, raw_pointer_types_removed=removed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mounted", type=Path)
    parser.add_argument("--link", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    if args.mounted:
        compile_mounted_sources(args.mounted, substitute, MARKER, allow_identical=True)
    elif args.link and args.output:
        links = json.loads(args.link.read_bytes())["source_library_sha256"]
        key, = [k for k in links if Path(k).name == "libtar_1_35_normalized_audit.a"]
        if args.replay:
            print(json.dumps(replay(args.link, key, args.output, transform=substitute), sort_keys=True))
        else:
            stage_selected_archive(args.link, args.output, key, MARKER, Path(__file__).name)
    else:
        parser.error("supply the link and the archive output directory")
