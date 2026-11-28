#!/usr/bin/env python3
"""Replay a recovered private-helper subset and recount the complete linked compiler inputs."""
# SPDX-License-Identifier: 0BSD
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

from audit_linked_pointers import check_identical_layer, measure
from check_cargo_private_inlines import ROOT, digest
from prepare_identical_archives import enroll, validate_link

LAYER = "closed_inline_groups"
METRICS = ("raw_pointer_types_removed", "private_helpers_removed")
PINNED = ("archive", "control_sha256", "control_binary_sha256", "parent_sources_sha256", "scanner_source_sha256")


def verify(parent, selected, active, whole, trial, output):
    whole_receipt = whole / "pilot.json"
    trial_receipt = trial / "pilot.json"
    inputs = {path: path.read_bytes() for path in (parent, selected, active, whole_receipt, trial_receipt)}
    baseline, release, manifest = (json.loads(inputs[path]) for path in (parent, selected, active))
    expected = validate_link(manifest, baseline["source_library_sha256"], baseline, LAYER)
    if release != {**baseline, LAYER: expected}:
        raise ValueError("selected multicall differs from the parent beyond its helper receipts")

    driver = [sys.executable, "-B", ROOT / "scripts/build_closed_inlines.py", "--link", parent]
    for folder in (whole, trial):
        subprocess.run([*driver, "--replay", folder], check=True)

    previous, row = (json.loads(inputs[path]) for path in (whole_receipt, trial_receipt))
    key = row["archive"]
    if key in manifest or any(row[field] != previous[field] for field in PINNED):
        raise ValueError("recovery must add an archive using the original compiler and sources")
    if previous["candidate_sha256"] == previous["control_sha256"] or row["candidate_sha256"] != row["control_sha256"]:
        raise ValueError("expected a differing whole archive and a byte-identical subset")
    if not 0 < row["raw_pointer_types_removed"] < previous["raw_pointer_types_removed"]:
        raise ValueError("subset must remove fewer pointer types than the whole trial")
    sites, original_sites = row["dead_sites"], previous["dead_sites"]
    if not sites.keys() < original_sites.keys() or any(original_sites[module] != group for module, group in sites.items()):
        raise ValueError("recovered helper sites differ from the original modules")

    output.mkdir(parents=True, exist_ok=True)
    combined = output / "combined.json"
    enroll(selected, combined, [trial], LAYER, previous_manifest=active)
    items = json.loads(combined.read_bytes())
    current = {**release, LAYER: validate_link(items, release["source_library_sha256"], release, LAYER)}
    before, after = measure(release), measure(current)
    check_identical_layer(release, current, before, after, LAYER)
    if any(path.read_bytes() != data for path, data in inputs.items()):
        raise ValueError("input release or receipts changed during replay")

    summary = dict(
        parent_link_sha256=sha256(inputs[parent]).hexdigest(),
        selected_link_sha256=sha256(inputs[selected]).hexdigest(),
        binary_sha256=release["binary"]["sha256"],
        archive_sha256=row["candidate_sha256"],
        whole_receipt_sha256=sha256(inputs[whole_receipt]).hexdigest(),
        trial_receipt_sha256=sha256(inputs[trial_receipt]).hexdigest(),
        combined_manifest_sha256=digest(combined),
        archive=key, modules=len(sites), archives=len(items),
        recovered={metric: row[metric] for metric in METRICS},
        combined={metric: sum(item["pilot"][metric] for item in items.values()) for metric in METRICS},
        counts={group: {"before": before[group]["raw_pointer_type_tokens"], "after": after[group]["raw_pointer_type_tokens"]}
                for group in ("all", "counting_identical_files_once")},
    )
    for name, data in (("recovered.json", {key: items[key]}), ("summary.json", summary)):
        (output / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("parent", "selected", "active", "whole", "trial", "output"):
        parser.add_argument(arg, type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.parent, args.selected, args.active, args.whole, args.trial, args.output), sort_keys=True))
