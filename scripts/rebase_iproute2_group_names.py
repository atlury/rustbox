#!/usr/bin/env python3
"""Check a device-group rewrite on a newer DS-field compiler source selection."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import json
from pathlib import Path
import subprocess
import sys

from build_checked_errno import replay
from build_group_names import substitute
from build_group_names_bridge import bridge_receipt
from check_cargo_private_inlines import ROOT, digest
from qualify_iproute2_combined_names import write_result
from stage_dsfield_archives import EVIDENCE, FIELD, candidate_path, parent_view
from test_iproute2_combined_names import EVIDENCE_DIR


def verify(link, pilot, baseline):
    link_sha = digest(link)
    baseline_sha = digest(baseline) if baseline else None
    release = json.loads(link.read_bytes())
    parent_view(release)
    history = json.loads(baseline.read_bytes()) if baseline else None
    row = json.loads((pilot / "pilot.json").read_bytes())
    key = row["archive"]
    selected = {str(candidate_path(r)): r for r in release[FIELD].values()}
    if (key not in selected
            or row["control_sha256"] != selected[key]["candidate_sha256"]
            or row["control_sha256"] != release["source_library_sha256"].get(key)
            or digest(ROOT / key) != row["control_sha256"]
            or row["control_binary_sha256"] != release["binary"]["sha256"]):
        raise ValueError("archive or source release differs from the expected DS-field parent")
    current = (bridge_receipt(link, key) if "rustc_archive" in row
               else replay(link, key, transform=substitute))
    if dict(current, candidate_sha256=digest(pilot / Path(key).name)) != row:
        raise ValueError("cold compiler receipt differs from independent source replay")
    prior = selected[key]["archive"]
    projection = json.loads((EVIDENCE_DIR / "iproute2-group-names-routing-sources.json").read_bytes())["engines"][prior]
    for field in ("helper_sha256", "canonical_sha256", "raw_pointer_types_removed", "module"):
        if row[field] != projection[field]:
            raise ValueError(f"device-group substitution differs in {field}")

    # A historical comparison certifies the two exact archive byte streams it exercised.
    # The compiler source receipt above is always reproduced on the newly selected parent.
    same_bytes = False
    if history:
        ancestor = history["archive"]
        if key != ancestor["archive"] or row["control_sha256"] != ancestor["control_sha256"]:
            raise ValueError("comparison belongs to a different control archive")
        same_bytes = row["candidate_sha256"] == ancestor["candidate_sha256"]
    reference = EVIDENCE_DIR / ("iproute2-group-names-pilot.json" if Path(key).name == "libip_audit.a"
                                else "iproute2-group-names-standalone.json")
    references = {"group": json.loads(reference.read_bytes()), "dsfield": json.loads(EVIDENCE.read_bytes())["verified"][prior]}
    results = {}
    for suite, command in (("group", ["test_group_names.py", "--link", link, "--pilot", pilot]),
                           ("dsfield", ["test_dsfield_names.py", pilot, link])):
        fields = ("profiles", "memcheck_runs", "oracle_compilers", "driver_sha256", "public_oracle_sha256")
        results[suite] = {k: references[suite][k] for k in fields}
        if suite == "dsfield":
            results[suite]["canonical_inputs"] = references[suite]["canonical_inputs"]
        if same_bytes:
            if history["comparisons"][suite] != results[suite]:
                raise ValueError(f"prior archive lacks the expected canonical {suite} coverage")
        else:
            observed = json.loads(subprocess.check_output([sys.executable, "-B", ROOT / "scripts" / command[0], *command[1:]]))
            if any(observed[k] != v for k, v in {**row, **results[suite]}.items()):
                raise ValueError(f"canonical {suite} comparisons differ on the selected sources")
    if digest(link) != link_sha or (baseline and digest(baseline) != baseline_sha):
        raise ValueError("release or baseline changed during verification")
    return dict(archive=row, link_sha256=link_sha, canonical_comparison_sha256=baseline_sha,
                comparisons=results, canonical_tests_rerun=not same_bytes)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("link", "pilot", "output"):
        p.add_argument(name, type=Path)
    p.add_argument("--baseline", type=Path, help="earlier canonical comparison of the same control and candidate")
    args = p.parse_args()
    write_result(args.output, verify(args.link, args.pilot, args.baseline))
