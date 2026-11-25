#!/usr/bin/env python3
"""Check duplicate archive accounting and recognition of fully enumerated name tables."""
# SPDX-License-Identifier: 0BSD
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import rank_shared_applet_modules as ranking

source = br'''pub unsafe extern "C" fn lookup() {
}
static mut names: [*mut ::core::ffi::c_char; 2] = [
    b"name\0" as *const u8 as *const ::core::ffi::c_char
        as *mut ::core::ffi::c_char,
    ::core::ptr::null::<::core::ffi::c_char>() as *mut ::core::ffi::c_char,
];
'''
table = {"name": "names", "capacity": 2, "literal_names": 1, "null_slots": 1}
assert ranking.generated_name_tables(source) == [table]
for bad in (source.replace(b"; 2]", b"; 3]"), source.replace(br'name\0', b'name'),
            source.replace(b"::core::ptr::null::<::core::ffi::c_char>()", b"dynamic_name()")):
    assert ranking.generated_name_tables(bad) == []


def compiler_inputs(link, *, inspect_module):
    for package, archive, module in (("one", "a", "names"), ("one", "a", "other_names"),
                                     ("one", "b", "names"), ("two", "c", "names")):
        inspect_module(Path(f"work/analysis/{package}/{archive}.a"), Path(f"{module}.rs"),
                       sha256(source).digest(), source)
    return {"binary_sha256": link["binary"]["sha256"]}


with tempfile.TemporaryDirectory() as scratch, patch.object(ranking, "measure", compiler_inputs):
    report = Path(scratch) / "link.json"
    report.write_text(json.dumps({"binary": {"sha256": "fixture"}}))
    result = ranking.rank(report)
    group, = result["modules"]
    assert group["archive_count"] == 2 and group["paths"] == ["names.rs", "other_names.rs"]
    assert result["groups"] == 1 and result["repeated_types_across_archives"] == 5
    assert group["static_name_tables"] == [table]
print("Duplicate paths within an archive and matches across packages were excluded; incomplete name tables were rejected.")

const_source = br'''pub static mut names: [*const ::core::ffi::c_char; 2] = [
    b"text\0" as *const u8 as *const ::core::ffi::c_char,
    ::core::ptr::null::<::core::ffi::c_char>(),
];
'''
decl, end, meta = next(ranking.name_table_spans(const_source))
assert meta == table and decl["public"] and decl["kind"] == b"const"
assert const_source[end:] == b"\n" and not ranking.generated_name_tables(const_source)
assert not list(ranking.name_table_spans(const_source.replace(b"null::<", b"unknown::<")))

def distinct_modules(link, *, inspect_module):
    for archive, module, data in (("a", "first", const_source), ("a", "second", const_source),
                                  ("b", "third", b"// different module\n" + const_source)):
        inspect_module(Path(f"work/analysis/example/{archive}.a"), Path(module + ".rs"), sha256(data).digest(), data)
    return {"binary_sha256": link["binary"]["sha256"]}

with tempfile.TemporaryDirectory() as scratch, patch.object(ranking, "measure", distinct_modules):
    report = Path(scratch) / "link.json"
    report.write_text(json.dumps({"binary": {"sha256": "fixture"}}))
    result = ranking.rank_tables(report)
    row, = result["tables"]
    assert result["copies"] == row["copies"] == 3
    assert result["raw_pointer_type_tokens"] == row["raw_pointer_type_tokens"] == 9
    assert row["public"] and row["pointee"] == "const" and len(row["archives"]) == 2
print("Identical table declarations were grouped across different modules and counted at each compiled path.")
