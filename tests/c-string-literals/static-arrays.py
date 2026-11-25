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
from verify_c_string_sources import syntax_tool

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
print("Matched the two top-level arrays and excluded both other casts.")
