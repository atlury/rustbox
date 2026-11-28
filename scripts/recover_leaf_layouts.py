#!/usr/bin/env python3
"""Retain groups of shared leaf layouts that jointly reproduce a previously differing engine archive."""
# SPDX-License-Identifier: 0BSD
import argparse
import fcntl
import json
from pathlib import Path
import subprocess
import sys
from tempfile import NamedTemporaryFile

from check_cargo_private_inlines import ROOT, digest
from recover_shared_stdio import search


def recover(link, ranking, whole, work, limit):
    parent = json.loads(link.read_bytes())
    original = json.loads((whole / "pilot.json").read_bytes())
    key = original["archive"]
    if (original["control_binary_sha256"] != parent["binary"]["sha256"]
            or parent["source_library_sha256"].get(key) != original["control_sha256"]
            or original["control_sha256"] == original["candidate_sha256"]):
        raise ValueError("expected a differing whole-archive trial against this release")
    driver = ROOT / "scripts" / ("build_direct_leaf_layouts.py" if "rustc_archive" in original else "build_leaf_layout_pilot.py")
    base = [sys.executable, "-B", driver, "--link", link, "--ranking", ranking, "--archive", key]
    layouts = original["leaf_layouts"]
    inputs = {p: digest(p) for p in (link, ranking, whole / "pilot.json", driver, ROOT / "scripts/build_leaf_layout_pilot.py",
                                      ROOT / "tools/private-inlines/src/bin/leaf-layouts.rs")}
    if "rustc_archive" in original:
        compiler = ROOT / "scripts/build_staged_c_strings.py"
        inputs[compiler] = digest(compiler)
    work.mkdir(parents=True, exist_ok=True)
    with (work / "recovery.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with (work / "whole-replay.log").open("ab") as log:
            subprocess.run([*base, "--layouts", *sorted(layouts), "--output", whole, "--replay"],
                           check=True, stdout=log, stderr=subprocess.STDOUT)

        def compare(number, group):
            if set(group) == layouts.keys():
                return False, original["candidate_sha256"]
            folder = work / f"trial-{number:03}"
            cmd = [*base, "--layouts", *group, "--output", folder]
            with folder.with_suffix(".log").open("ab") as log:
                if not folder.exists():
                    subprocess.run(cmd, check=True, stdout=log, stderr=subprocess.STDOUT)
                subprocess.run([*cmd, "--replay"], check=True, stdout=log, stderr=subprocess.STDOUT)
            row = json.loads((folder / "pilot.json").read_bytes())
            if (any(row.get(field) != original.get(field) for field in
                    ("archive", "control_binary_sha256", "control_sha256", "parent_sources_sha256", "compiler_selected_sources", "rustc_archive", "cargo_archive"))
                    or row["leaf_layouts"] != {name: layouts[name] for name in group}
                    or row["raw_pointer_types_removed"] != sum(layouts[name]["pointer_fields"] * len(layouts[name]["consumers"]) for name in group)):
                raise ValueError(f"layout group differs from its whole-archive receipt in {folder}")
            identical = row["candidate_sha256"] == row["control_sha256"]
            print(folder.name, len(group), row["raw_pointer_types_removed"], identical, flush=True)
            return identical, row["candidate_sha256"]

        accepted, trace = search(layouts, limit, compare)
        result = dict(archive=key, link_sha256=inputs[link], ranking_sha256=inputs[ranking],
                      whole_receipt_sha256=inputs[whole / "pilot.json"], accepted=accepted, trials=trace,
                      raw_pointer_types_removed=0, verified_directory=None)
        if accepted:
            number = max(n for n, trial in enumerate(trace, 1) if trial["identical"] and trial["modules"] == accepted)
            folder = work / f"trial-{number:03}"
            row = json.loads((folder / "pilot.json").read_bytes())
            result.update(raw_pointer_types_removed=row["raw_pointer_types_removed"], verified_directory=folder.name,
                          pilot_sha256=digest(folder / "pilot.json"))
        if any(digest(p) != checksum for p, checksum in inputs.items()):
            raise ValueError("input changed during the recovery")
        with NamedTemporaryFile("w", dir=work, delete=False) as staged:
            json.dump(result, staged, indent=2, sort_keys=True)
            staged.write("\n")
        Path(staged.name).replace(work / "results.json")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("link", "ranking", "whole", "output"):
        p.add_argument(name, type=Path)
    p.add_argument("--limit", type=int, default=8)
    args = p.parse_args()
    if args.limit < 1:
        p.error("--limit must be positive")
    recover(args.link, args.ranking, args.whole, args.output, args.limit)
