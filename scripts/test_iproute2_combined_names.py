#!/usr/bin/env python3
"""Verify that a group-name substitution preserves the previously qualified DS field reader."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import json
from pathlib import Path
import subprocess
import sys

from build_group_names import substitute
from build_checked_errno import replay
from check_cargo_private_inlines import ROOT, digest
from stage_dsfield_archives import EVIDENCE, candidate_path, parent_view

EVIDENCE_DIR = ROOT / "evidence"


def check(link, pilot):
    parent = json.loads(link.read_bytes())
    if "iproute2_dsfield_names" not in parent:
        raise ValueError("expected a release containing qualified DS field readers")
    parent_view(parent)
    row = json.loads((pilot / "pilot.json").read_bytes())
    key = Path(row["archive"])
    if parent["source_library_sha256"].get(str(key)) != row["control_sha256"]:
        raise ValueError("group-name control differs from the selected DS field archive")
    previous_key, = [k for k, r in parent["iproute2_dsfield_names"].items() if candidate_path(r) == key]
    ds = json.loads(EVIDENCE.read_bytes())["verified"][previous_key]
    original_groups = EVIDENCE_DIR / "iproute2-group-names-routing-sources.json"
    group_projection = json.loads(original_groups.read_bytes())["engines"][previous_key]
    if (row["parent_sources_sha256"] != ds["candidate_sources_sha256"]
            or row["control_module_sha256"] != ds["candidate_module_sha256"]
            or row["candidate_module_sha256"] != group_projection["with_dsfield_module_sha256"]
            or row["helper_sha256"] != group_projection["helper_sha256"]):
        raise ValueError("combined module differs from the two independently replayed substitutions")
    if "rustc_archive" in row:
        from build_group_names_bridge import bridge_receipt
        restored = bridge_receipt(link, str(key))
    else:
        restored = replay(link, str(key), transform=substitute)
    if dict(restored, candidate_sha256=digest(pilot / key.name)) != row:
        raise ValueError("cold build differs from the combined compiler source replay")
    public = key.name == "libip_audit.a"
    reference = EVIDENCE_DIR / ("iproute2-group-names-pilot.json" if public else "iproute2-group-names-standalone.json")
    groups = json.loads(reference.read_bytes())
    results = {}
    for name, baseline, invocation in (
            ("group", groups, ["test_group_names.py", "--link", link, "--pilot", pilot]),
            ("dsfield", ds, ["test_dsfield_names.py", pilot, link])):
        script, *arguments = invocation
        observed = json.loads(subprocess.check_output([sys.executable, "-B", ROOT / "scripts" / script, *arguments]))
        fields = ["profiles", "memcheck_runs", "oracle_compilers", "driver_sha256", "public_oracle_sha256"]
        if name == "dsfield":
            fields.append("canonical_inputs")
        if any(observed[k] != baseline[k] for k in fields) or any(observed[k] != v for k,v in row.items()):
            raise ValueError(f"{name} canonical observations or tested archive changed")
        results[name] = {k:observed[k] for k in fields}
    return dict(archive=row, link_sha256=digest(link), group_baseline_sha256=digest(reference),
                combined_projection_sha256=digest(original_groups), dsfield_baseline_sha256=digest(EVIDENCE),
                raw_pointer_types_removed=ds["raw_pointer_types_removed"] + row["raw_pointer_types_removed"],
                comparisons=results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path)
    parser.add_argument("pilot", type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.link, args.pilot), sort_keys=True, indent=2))
