#!/usr/bin/env python3
"""Recover jointly byte-identical module subsets when a static-array candidate changes archive bytes."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import fcntl
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from build_c_string_literal_pilot import build
from check_cargo_private_inlines import digest
from recover_shared_stdio import search
from verify_c_string_sources import verify


def refine(link, candidate, output, limit):
    whole_path = candidate / "pilot.json"
    comparison_path = candidate / "comparison.json"
    original = whole_path.read_bytes()
    comparison = comparison_path.read_bytes()
    whole, compare = json.loads(original), json.loads(comparison)
    if ("static_array_selector_sha256" not in whole or compare["candidate"] != whole or compare["byte_identical"]
            or whole["control_sha256"] == whole["candidate_sha256"] or len(whole["modules"]) < 2 or limit < 1):
        raise ValueError("expected a differing static-array build with multiple modules")
    link_sha = digest(link)
    if json.loads(link.read_bytes())["binary"]["sha256"] != whole["control_binary_sha256"]:
        raise ValueError("static-array candidate belongs to another linked executable")
    verify(link, candidate)
    key = Path(whole["archive"])
    fields = ("archive", "parent_sources_sha256", "control_sha256", "control_binary_sha256",
              "static_array_selector_sha256", "compiler_selected_sources")
    output.mkdir(exist_ok=True)

    def trial(_, modules):
        if modules == sorted(whole["modules"]):
            return False, whole["candidate_sha256"]
        # Key by the actual selection so that a retry or changed trial budget
        # reuses exactly the same set of compiler inputs.
        name = sha256(json.dumps(modules).encode()).hexdigest()
        folder = output / name
        with (output / (name + ".lock")).open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not folder.exists():
                build(link, folder, key, modules=modules, static_arrays=True)
            row = json.loads((folder / "pilot.json").read_bytes())
            if (any(row[k] != whole[k] for k in fields) or row.get("legacy_compiler") != whole.get("legacy_compiler")
                    or row["modules"] != {m: whole["modules"][m] for m in modules}):
                raise ValueError("refinement changed its compiler parent or chosen literals")
            verify(link, folder)
        same = row["candidate_sha256"] == row["control_sha256"]
        print(f"{len(modules)} modules, {row['c_string_literals']} literals, byte-identical={same}", flush=True)
        return same, row["candidate_sha256"]

    accepted, trace = search(whole["modules"], limit, trial)
    if digest(link) != link_sha or whole_path.read_bytes() != original or comparison_path.read_bytes() != comparison:
        raise ValueError("link selection or source receipts changed during refinement")
    winner = sha256(json.dumps(accepted).encode()).hexdigest() if accepted else None
    selected = json.loads((output / winner / "pilot.json").read_bytes()) if winner else None
    result = dict(archive=str(key), link_report_sha256=link_sha, original_candidate_sha256=whole["candidate_sha256"],
                  verified_directory=winner, selected=selected, trials=trace,
                  raw_pointer_types_removed=selected["raw_pointer_types_removed"] if selected else 0)
    with TemporaryDirectory(dir=output) as tmp:
        stage = Path(tmp) / "results.json"
        stage.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        stage.replace(output / "results.json")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("link", "candidate", "output"):
        p.add_argument(name, type=Path)
    p.add_argument("--limit", type=int, default=6, help="maximum subset comparisons")
    args = p.parse_args()
    refine(args.link, args.candidate, args.output, args.limit)
