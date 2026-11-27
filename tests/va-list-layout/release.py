#!/usr/bin/env python3
"""Replay the e4defrag layout after the C-string layer and reject incomplete or reordered sources."""
# SPDX-License-Identifier: GPL-2.0-only
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_linked_pointers import check_identical_layer, measure
from build_va_list_layout_pilot import TAG, substitute
from cargo_source_parent import cargo_origin
from prepare_identical_archives import validate_link

parent = json.loads(Path(sys.argv[1]).read_bytes())
manifest = json.loads(Path(sys.argv[2]).read_bytes())
field = "shared_va_list_layouts"
records = validate_link(manifest, parent["source_library_sha256"], parent, field)
key, = records
pair = (cargo_origin(parent, key), Path(key))
assert key in parent["native_c_strings"]
selected = {**parent, field: records}
before, after = [measure(link, archive_pair=pair) for link in (parent, selected)]
check_identical_layer(parent, selected, before, after, field)
assert after["shared_va_list_layout_deltas"] == {key: 100}
assert before["all"]["raw_pointer_type_tokens"] - after["all"]["raw_pointer_type_tokens"] == 100
invalid = []
for attr in ("provider", "candidate_sources_sha256", "control_sha256", "reexporting_modules"):
    bad = deepcopy(selected)
    row = bad[field][key]
    row[attr] = row[attr][1:] if attr == "reexporting_modules" else "different"
    invalid.append((attr, bad))
bad = deepcopy(selected)
del bad["native_c_strings"][key]
invalid.append(("absent C-string parent", bad))
for case, bad in invalid:
    try:
        measure(bad, archive_pair=pair)
    except ValueError:
        continue
    raise AssertionError("accepted " + case)
print("Replayed 100 shared fields after the C-string layer and rejected five mismatches.")

with TemporaryDirectory() as tmp:
    crate = Path(tmp)
    (crate / "lib.rs").write_bytes(b"")
    inputs = {"a.rs": TAG, "b.rs": TAG, "c.rs": TAG, "different.rs": TAG.replace(b"gp_offset", b"other")}
    changed, facts = substitute(crate, inputs, inputs.__getitem__, modules=["c.rs"])
    assert set(changed) == {"c.rs"} and facts["provider"] == "a.rs" and facts["raw_pointer_types_removed"] == 2
    for selection in ([], ["a.rs"], ["b.rs", "b.rs"], ["different.rs"], ["unknown.rs"]):
        try:
            substitute(crate, inputs, inputs.__getitem__, modules=selection)
        except ValueError:
            continue
        raise AssertionError(f"accepted invalid module selection {selection}")
print("Replayed a partial variadic selection and rejected five invalid selections.")
