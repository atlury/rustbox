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
from prepare_identical_archives import selected_receipts


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
    inputs = selected_receipts(parent, key, layer)
    parent = {"binary": parent["binary"], "source_library_sha256": {key: parent["source_library_sha256"][key]},
              **{field: {key: receipt} for field, receipt in inputs.items()}}
    candidate = {**parent, layer: {key: row}}
    before, after = measure(parent), measure(candidate)
    check_identical_layer(parent, candidate, before, after, layer)
    assert before["all"]["raw_pointer_type_tokens"] - after["all"]["raw_pointer_type_tokens"] == row["raw_pointer_types_removed"]
    assert after["all"]["as_ptr_calls"] - before["all"]["as_ptr_calls"] == row["c_string_literals"]
    for field in ("candidate_sha256", "parent_sources_sha256", "candidate_sources_sha256"):
        changed = {**candidate, layer: {key: {**row, field: "0" * 64}}}
        rejected(lambda: measure(changed))
    changed = deepcopy(candidate)
    changed[layer][key]["modules"].pop(next(iter(row["modules"])))
    rejected(lambda: measure(changed))
    if "shared_stdio_layouts" in parent:
        rejected(lambda: measure({k: v for k, v in candidate.items() if k != "shared_stdio_layouts"}))
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
