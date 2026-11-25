#!/usr/bin/env python3
"""A later cleanup has byte offsets in the source produced by its parent."""
# SPDX-License-Identifier: 0BSD
import hashlib
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_next_inline_layer import apply_receipt, new_leaf_estimate
from inline_source_layout import WHITESPACE


def receipt(name, start, end, expected, **kwargs):
    return {"ranges": {name: [[start, end]]},
            "sources": {name: hashlib.sha256(expected).hexdigest()}, **kwargs}


data = b"#[inline]\nfn leaf() {}\n#[inline]\nfn already_unused() {}\n#[inline]\nfn caller() { leaf(); }"
assert new_leaf_estimate(data, [(data.rindex(b"#[inline]"), len(data))]) == 1
assert new_leaf_estimate(data, []) == 0

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    (root / "src").mkdir()
    name = "src/demo.rs"
    file = root / name
    original = b"fn outer(_: *const u8) {}\nfn inner(_: *mut u8) {}\nfn keep() {}\n"
    first_end = original.index(b"\n")
    first = original[first_end:]
    second_end = first.index(b"\nfn keep")
    padded = first[:1] + first[1:second_end].translate(WHITESPACE) + first[second_end:]
    parent = receipt(name, 0, first_end, first, source_directory="src")
    child = receipt(name, 1, second_end, padded, source_layout="byte_offsets")
    file.write_bytes(original)
    assert apply_receipt(root, parent, {name}) == 1 and file.read_bytes() == first
    assert apply_receipt(root, child, {name}) == 1 and file.read_bytes() == padded
    for bad, message in ((child, "differs"), (dict(parent, source_directory="other"), "outside"),
                         (dict(parent, source_layout="other"), "layout")):
        file.write_bytes(original)
        try:
            apply_receipt(root, bad, {name})
        except ValueError as error:
            assert message in str(error)
        else:
            raise AssertionError("accepted a cleanup on the wrong input")
print("Layered cleanup coordinates, layouts, scope and parent ordering passed.")
