#!/usr/bin/env python3
"""Recover jointly byte-identical module groups from a differing private-helper archive."""
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


def recover(link, whole, output, limit):
    original = json.loads((whole / "pilot.json").read_bytes())
    key = original["archive"]
    driver = [sys.executable, "-B", ROOT / "scripts/build_closed_inlines.py", "--link", link]
    subprocess.run([*driver, "--replay", whole], check=True)
    if original["candidate_sha256"] == original["control_sha256"]:
        raise ValueError("recovery requires a differing whole archive")
    output.mkdir(parents=True, exist_ok=True)

    def compare(number, modules):
        if set(modules) == original["dead_sites"].keys():
            return False, original["candidate_sha256"]
        trial = output / f"trial-{number:03}"
        with trial.with_suffix(".log").open("ab") as log:
            if not trial.exists():
                subprocess.run([*driver, "--archive", key, "--output", trial, "--modules", *modules],
                               stdout=log, stderr=subprocess.STDOUT, check=True)
            subprocess.run([*driver, "--replay", trial], stdout=log, stderr=subprocess.STDOUT, check=True)
        row = json.loads((trial / "pilot.json").read_bytes())
        pinned = ("archive", "control_binary_sha256", "control_sha256", "parent_sources_sha256", "scanner_source_sha256")
        if (any(row[k] != original[k] for k in pinned)
                or row["dead_sites"] != {name: original["dead_sites"][name] for name in modules}):
            raise ValueError("subset differs from the independently verified compiler sites")
        identical = row["candidate_sha256"] == row["control_sha256"]
        print(f'Trial {number} checked {len(modules)} modules, identical={identical}, declarations={row["raw_pointer_types_removed"]}', flush=True)
        return identical, row["candidate_sha256"]

    with (output / "recovery.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        accepted, trace = search(original["dead_sites"], limit, compare)
        good = [i for i, entry in enumerate(trace, 1) if entry["identical"]]
        result = dict(archive=key, whole_receipt_sha256=digest(whole / "pilot.json"), trace=trace,
                      verified_directory=None, raw_pointer_types_removed=0)
        if good:
            trial = output / f"trial-{good[-1]:03}"
            row = json.loads((trial / "pilot.json").read_bytes())
            if sorted(row["dead_sites"]) != accepted:
                raise ValueError("recovery result differs from its last jointly verified build")
            result.update(verified_directory=trial.name, raw_pointer_types_removed=row["raw_pointer_types_removed"])
        with NamedTemporaryFile(mode="w", dir=output, delete=False) as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write("\n")
        Path(stream.name).replace(output / "results.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path)
    parser.add_argument("whole", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--limit", type=int, help="maximum subset trials", default=sys.maxsize)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    recover(args.link, args.whole, args.output, args.limit)
