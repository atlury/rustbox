#!/usr/bin/env python3
"""Check that whole-array candidates exclude local expressions and preserve UTF-8 byte positions."""
# SPDX-License-Identifier: 0BSD
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from verify_c_string_sources import replay, syntax_tool
from build_c_string_literal_pilot import rewrite
from check_e2fsprogs_dirhash_arrays import source_list_digest
from hashlib import sha256

cast = b' as *const u8 as *const ::core::ffi::c_char'
source = ('// multibyte prefix é and misleading brackets []\r\n').encode() + b'''
static mut A: [*const ::core::ffi::c_char; 1] = [b"]\\0"CAST];
const B: [*const ::core::ffi::c_char; 1] = [
    b"[\\0"CAST
];
fn local() { let _ = [b"local\\0"CAST]; }
static mut C: *const ::core::ffi::c_char = b"outside\\0"CAST;
'''.replace(b'CAST', cast)
with TemporaryDirectory() as tmp:
    root = Path(tmp)
    (root / "probe.rs").write_bytes(source)
    def scan(name):
        return json.loads(subprocess.check_output([syntax_tool(name), root], input=b'["probe.rs"]'))["probe.rs"]
    spans = scan("static-array-spans")
    edits = scan("c-string-literals")
    assert len(spans) == 2 and len(edits) == 4
    covered = [source[start:end] for start, end, _ in edits if any(left <= start < end <= right for left, right in spans)]
    assert covered == [b'b"]\\0"' + cast, b'b"[\\0"' + cast]
    replacements, row = rewrite(root, ["probe.rs"], syntax_tool("c-string-literals"),
                                array_tool=syntax_tool("static-array-spans"))
    new = replacements["probe.rs"]
    assert row["raw_pointer_types_removed"] == 4 and row["modules"] == {"probe.rs": 2}
    assert new == source.replace(covered[0], b'c"]".as_ptr()').replace(covered[1], b'c"[".as_ptr()')
    parent = {"probe.rs": sha256(source).hexdigest()}
    row.update(compiler_selected_sources=1, parent_sources_sha256=source_list_digest(parent),
               candidate_sources_sha256=source_list_digest({"probe.rs": sha256(new).hexdigest()}))
    def repeat(receipt):
        return replay(parent, lambda _: source, receipt, syntax_tool("c-string-literals"))
    assert repeat(row) == replacements
    for broken in (dict(row, static_array_selector_sha256="changed"), dict(row, modules={"probe.rs": 4}),
                   {k: v for k, v in row.items() if k != "static_array_selector_sha256"}):
        try:
            repeat(broken)
        except ValueError:
            continue
        raise AssertionError("accepted a stale static-array selection")
print("Matched both array literals, preserved both other casts, and rejected three invalid receipts.")
