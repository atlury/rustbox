#!/usr/bin/env python3
"""Check the exact gzip cold-build receipt and reject altered layouts, alias widths and selection."""
# SPDX-License-Identifier: GPL-3.0-or-later
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_linked_pointers import check_shared_stdio, measure
from check_cargo_private_inlines import layout
from share_stdio_layout import GZIP_OWNER, declarations, eligible, share
from recover_shared_stdio import search

release_file = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "work/analysis/rustbox-multicall-link.json"
release = json.loads(release_file.read_bytes())
sample = json.loads((ROOT / "evidence/gzip-stdio-layout-pilot.json").read_bytes())
key = sample["archive"]
archive = Path(key)
src, _ = layout(archive)
data = (ROOT / src / GZIP_OWNER).read_bytes()
assert len(declarations(data)) == 4
copy = share(data, GZIP_OWNER)
assert copy.count(b"\n") == data.count(b"\n") and copy.count(b"pub use crate::src::normalized_source::gzip::_IO_") == 4
for invalid in (data.replace(b"pub type __off_t = ::core::ffi::c_long;", b"pub type __off_t = u32;"),
                data.replace(b"pub _IO_read_ptr: *mut", b"pub _IO_read_ptr: *const"),
                data.replace(b"pub struct _IO_marker {", b"pub struct MismatchedMarker {")):
    assert not eligible(invalid)
    try:
        share(invalid, GZIP_OWNER)
    except ValueError:
        continue
    raise AssertionError("accepted a different FILE layout")
selection = {"binary": release["binary"]}
for field in ("source_library_sha256", "linked_private_inline_proofs", "linked_second_inline_proofs", "linked_foreign_declaration_proofs"):
    if key in release.get(field, {}):
        selection[field] = {key: release[field][key]}
selected = dict(selection, shared_stdio_layouts={key: sample})
before, after = measure(selection), measure(selected)
check_shared_stdio(selection, selected, before, after)
assert after["shared_stdio_layout_deltas"] == {key: 468}
for field, value in (("candidate_sha256", "0" * 64), ("candidate_sources_sha256", "0" * 64),
                     ("provider", "../other.rs"), ("reexporting_modules", sample["reexporting_modules"][:-1])):
    changed = deepcopy(selected)
    changed["shared_stdio_layouts"][key][field] = value
    try:
        measure(changed)
    except ValueError:
        continue
    raise AssertionError(f"accepted incorrect {field}")
bad_link = dict(selected, binary=dict(selected["binary"], sha256="0" * 64))
try:
    check_shared_stdio(selection, bad_link, before, after)
except ValueError:
    pass
else:
    raise AssertionError("accepted a different ELF")
print("Replayed all 26 gzip replacements and rejected altered layouts, compiler inputs, archive selections and ELF.")

# A pair can change archive bytes even though both modules pass in isolation.
# Selecting by union must retain only a jointly reproducible group.
def compatible(n, items):
    return ("b" not in items and not {"a", "c"} <= set(items), str(n))

accepted, trace = search(["a", "b", "c", "d", "e"], 12, compatible)
assert accepted and compatible(0, accepted)[0]
assert any(t["modules"] == accepted and t["identical"] for t in trace)
bounded, short = search(list("abcdefg"), 2, compatible)
assert len(short) == 2 and compatible(0, bounded)[0]
print("Subset recovery kept only jointly tested modules and respected the trial limit.")
