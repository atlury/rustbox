#!/usr/bin/env python3
"""Replace file's compression magic pointer union and unchecked callbacks with borrowed byte headers."""
# SPDX-License-Identifier: 0BSD
import argparse
import ast
from hashlib import sha256
import json
from pathlib import Path
import re

from build_checked_errno import replay
from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import ROOT, digest
from prune_private_inlines import POINTER

MODULE = "src/compress.rs"
NATIVE = ROOT / "compat/file/compression_header.rs"
MARKER = ".rustbox-file-compression-headers"
TABLE_START = b"static mut compr: [C2RustUnnamed_13; 15]"
TABLE_END = b"pub const METH_FROZEN"
PREDICATES = b'unsafe extern "C" fn zlibcmp('
LOOP = b"        let mut zm: ::core::ffi::c_int = 0;"
MATCH = b"            if !(zm == 0) {"
MAGIC = re.compile(rb'            u: C2RustUnnamed_14 \{\n                magic: (b"(?:\\.|[^"\\])*") as \*const u8 as \*const ::core::ffi::c_char,\n            \},\n            maglen: (\d+) as ::core::ffi::c_int,')
CALLBACK = re.compile(rb'            u: C2RustUnnamed_14 \{\n                func: Some\(\s+(lzmacmp|zlibcmp)\s+as unsafe extern "C" fn\(\s+\*const ::core::ffi::c_uchar,\s+\) -> ::core::ffi::c_int,\s+\),\s+\},\n            maglen: -\((\d+) as ::core::ffi::c_int\),')


REGION_DIGESTS = [
    "022e7963912cc0c5c4c0fdaf041d58dc1cb119327b5a53528f757ccd8bf13cde",
    "6f872d5a9d78630176a90fd2e9d85af83b2d8d8f8a6e20bd11f0476b23c48501",
    "dcd9c6004011f1c7c02afac0ac0d227be1ff47b5b72930b51c2ade94f063bf7d",
    "9a95e919c56a6823a141ee371f9fd551b4c9d6a58c3c4afe20e5f8be5425fb6a",
]


def region(data, start, end):
    if data.count(start) != 1 or data.count(end) != 1:
        raise ValueError("ambiguous file compression region")
    return data[data.index(start):data.index(end)]


def substitute(crate, sources):
    data = (crate / MODULE).read_bytes()
    if sources[MODULE] != sha256(data).hexdigest():
        raise ValueError("unexpected compression module bytes")
    table = region(data, TABLE_START, TABLE_END)
    predicates = region(data, PREDICATES, b"pub const gzip_flags:")
    union = region(data, b"#[derive(Copy, Clone)]\n#[repr(C)]\npub union C2RustUnnamed_14", b"pub const _ISalnum:")
    dispatch = region(data, LOOP, MATCH) + MATCH
    regions = [table, predicates, union, dispatch]
    if [sha256(r).hexdigest() for r in regions] != REGION_DIGESTS:
        raise ValueError("compression table, predicates or dispatcher differ from the pinned translation")
    headers = []
    def literal(m):
        # The Rust generator uses the common C/Python byte escapes in this pinned table.
        spelling, size = m[1], int(m[2])
        value = ast.literal_eval(spelling.decode("ascii"))
        if len(value) != size + 1 or value[-1] or not spelling.endswith(b'\\0"'):
            raise ValueError("magic string length disagrees with the table")
        headers.append(value[:-1].hex())
        return b"            header: CompressionHeader::Magic(" + spelling[:-3] + b'"),'
    def callback(m):
        name, size = m[1], int(m[2])
        kind, expected = {b"lzmacmp": (b"Lzma",13), b"zlibcmp": (b"Zlib",2)}[name]
        if size != expected:
            raise ValueError("compression predicate length changed")
        return b"            header: CompressionHeader::" + kind + b","
    updated, literals = MAGIC.subn(literal, table)
    updated, callbacks = CALLBACK.subn(callback, updated)
    if (literals, callbacks) != (13, 2):
        raise ValueError("expected all 15 canonical compression methods")
    fields = b"    pub u: C2RustUnnamed_14,\n    pub maglen: ::core::ffi::c_int,"
    if data.count(fields) != 1:
        raise ValueError("unexpected compression row layout")
    match = b"""        let header = compr[i as usize].header;
        if nbytes >= header.length() {
            // The caller supplies nbytes readable bytes. Borrow only the prefix used by this method.
            let prefix = ::core::slice::from_raw_parts(buf, header.length());
            if header.matches(prefix) {"""
    helper = NATIVE.read_bytes()
    result = data.replace(table, updated).replace(fields, b"    header: CompressionHeader,").replace(union, helper + b"\n")
    result = result.replace(predicates, b"").replace(dispatch, match)
    for symbol in (b"memcmp", b"abs", b"file_bigendian"):
        declaration = re.compile(rb"^    fn " + symbol + rb"\([^;]*?;\n", re.M)
        if len(re.findall(rb"\b"+symbol+rb"\b",result)) != 1:
            raise ValueError("a removed predicate still shares a foreign function")
        result, count = declaration.subn(b"",result)
        if count != 1:
            raise ValueError("compression foreign declaration missing")
    if b"C2RustUnnamed_14" in result or b".maglen" in result:
        raise ValueError("compression union still referenced")
    changes = dict(raw_pointer_types_removed=len(POINTER.findall(data))-len(POINTER.findall(result)),
                   unchecked_offsets_removed=data.count(b".offset(")-result.count(b".offset("),
                   predicates=callbacks, magic_prefixes=headers, helper_sha256=digest(NATIVE))
    return {MODULE:result}, changes


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--link", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mounted", type=Path)
    parser.add_argument("--replay", type=Path)
    args=parser.parse_args()
    if args.mounted:
        compile_mounted_sources(args.mounted, substitute, MARKER, allow_identical=True)
    elif args.link:
        parent=json.loads(args.link.read_bytes())
        key, = [k for k in parent["source_library_sha256"] if Path(k).name=="libfile_5_48_normalized_audit.a"]
        if args.replay:
            replay(args.link, key, args.replay, transform=substitute)
        elif args.output:
            stage_selected_archive(args.link,args.output,key,MARKER,Path(__file__).name)
        else: parser.error("provide --output or --replay")
    else: parser.error("expected --link")
