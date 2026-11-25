#!/usr/bin/env python3
"""Check the ncurses release selection and reject stale fields, providers and module hashes."""
# SPDX-License-Identifier: MIT
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_linked_pointers import check_identical_layer, measure
from cargo_source_parent import cargo_origin
from prepare_identical_archives import validate_link

parent, manifest = [json.loads(Path(arg).read_bytes()) for arg in sys.argv[1:]]
layer = "shared_ncurses_termtypes"
rows = validate_link(manifest, parent["source_library_sha256"], parent, layer)
key, = rows
pair = (cargo_origin(parent, key), Path(key))
selected = {**parent, layer: rows}
before, after = [measure(link, archive_pair=pair) for link in (parent, selected)]
check_identical_layer(parent, selected, before, after, layer)
assert after["shared_ncurses_termtype_deltas"] == {key: 2439}
for attr in ("declarations_sha256", "providers", "reexporting_modules", "candidate_sources_sha256", "candidate_sha256"):
    changed = deepcopy(selected)
    row = changed[layer][key]
    if attr == "declarations_sha256":
        row[attr]["termtype"] = row[attr]["termtype2"]
    elif attr == "providers":
        row[attr]["termtype"] = row["reexporting_modules"]["termtype"][0]
    elif attr == "reexporting_modules":
        row[attr]["termtype2"].pop()
    else:
        row[attr] = "0" * 64
    try:
        measure(changed, archive_pair=pair)
    except ValueError:
        continue
    raise AssertionError("accepted " + attr)
print("Replayed 2,439 fields and rejected five changed terminal-layout receipts.")
