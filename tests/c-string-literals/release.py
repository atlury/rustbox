#!/usr/bin/env python3
"""Verify literal inventory, proof of the complete archive and ordering after shared stdio."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_linked_pointers import check_identical_layer, measure
from cargo_source_parent import cargo_origin, pinned_parent, row_origin


def rejected(action):
    try:
        action()
    except ValueError:
        return
    raise AssertionError("invalid compiler receipt accepted")


def run(link, pilot):
    parent = json.loads(link.read_bytes())
    row = json.loads(pilot.read_bytes())
    key = row["archive"]
    layer = "native_c_strings"
    origin = cargo_origin(parent, key)
    assert str(origin) == row_origin(row)
    pair = (origin, Path(key))
    parent.pop(layer, None)
    candidate = {**parent, layer: {key: row}}
    def scoped(selection):
        return measure(selection, archive_pair=pair)
    before, after = scoped(parent), scoped(candidate)
    check_identical_layer(parent, candidate, before, after, layer)
    assert before["all"]["raw_pointer_type_tokens"] - after["all"]["raw_pointer_type_tokens"] == row["raw_pointer_types_removed"]
    assert after["all"]["as_ptr_calls"] - before["all"]["as_ptr_calls"] == row["c_string_literals"]
    for field in ("candidate_sha256", "parent_sources_sha256", "candidate_sources_sha256"):
        changed = {**candidate, layer: {key: {**row, field: "0" * 64}}}
        rejected(lambda: scoped(changed))
    changed = deepcopy(candidate)
    changed[layer][key]["modules"].pop(next(iter(row["modules"])))
    rejected(lambda: scoped(changed))
    if origin != Path(key):
        historical = pinned_parent(key, row)
        historical["binary"] = parent["binary"]
        from prepare_identical_archives import selected_receipts
        for field, value in selected_receipts(parent, key, layer).items():
            location = key if field == "shared_stdio_layouts" else str(origin)
            historical.setdefault(field, {})[location] = value
        assert scoped(historical)["all"] == before["all"]
        broken = {**parent, "source_library_sha256": {**parent["source_library_sha256"], key: "0" * 64}}
        rejected(lambda: scoped(broken))
        rejected(lambda: pinned_parent(key, {**row, ("rustc_archive" if "rustc_archive" in row else "cargo_archive"): "work/analysis/unknown/target/release/libother.a"}))
    if key in parent.get("shared_stdio_layouts", {}):
        rejected(lambda: scoped({k: v for k, v in candidate.items() if k != "shared_stdio_layouts"}))
    changed = deepcopy(after)
    changed["all"]["as_ptr_calls"] -= 1
    rejected(lambda: check_identical_layer(parent, candidate, before, changed, layer))
    print(f"Verified {row['c_string_literals']} compiled literals, their pointer extractions and source receipts in {Path(key).name}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path)
    parser.add_argument("pilot", type=Path)
    args = parser.parse_args()
    run(args.link, args.pilot)
