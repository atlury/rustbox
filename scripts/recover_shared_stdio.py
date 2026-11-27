#!/usr/bin/env python3
"""Find a jointly byte-identical subset when sharing every copy of an ABI layout changed an archive."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from collections import deque
import json
from pathlib import Path
import subprocess
import sys

from check_cargo_private_inlines import digest


def search(modules, limit, compare):
    def halves(items):
        mid = len(items) // 2
        return [part for part in (items[:mid], items[mid:]) if part]
    pending = deque(halves(sorted(modules))) if len(modules) > 1 else deque()
    accepted = set()
    trace = []
    while pending and len(trace) < limit:
        group = pending.popleft()
        combined = sorted(accepted.union(group))
        match, sha = compare(len(trace) + 1, combined)
        trace.append(dict(modules=combined, identical=match, archive_sha256=sha))
        if match:
            accepted.update(group)
        elif len(group) > 1:
            pending.extend(halves(group))
    return sorted(accepted), trace


def recover(link, whole, out, limit, kind="stdio"):
    row = json.loads((whole / "pilot.json").read_bytes())
    key = row["archive"]
    parent = json.loads(link.read_bytes())
    if (row["control_binary_sha256"] != parent["binary"]["sha256"] or row["control_sha256"] != parent["source_library_sha256"][key]
            or digest(whole / Path(key).name) != row["candidate_sha256"] or row["candidate_sha256"] == row["control_sha256"]):
        raise ValueError("expected a complete, differing pilot against this control")
    fields = 2 if kind == "va-list" else 18
    if row["raw_pointer_types_removed"] != fields * len(row["reexporting_modules"]):
        raise ValueError("whole archive receipt differs from the requested layout")
    if kind == "va-list":
        # Byte-identical release layers may have different Rust compiler inputs.
        from verify_shared_layout_sources import verify
        verify(link, whole, kind)
    out.mkdir(exist_ok=True)

    def compare(n, modules):
        if kind == "va-list" and modules == sorted(row["reexporting_modules"]):
            print("Reused the verified, differing whole-archive result.", flush=True)
            return False, row["candidate_sha256"]
        trial = out / f"trial-{n:02d}"
        if not trial.exists():
            with (out / f"trial-{n:02d}.log").open("wb") as log:
                subprocess.run([sys.executable, "-B", Path(__file__).resolve(), "--trial", link, whole, trial,
                                "--kind", kind, "--modules", *modules], stdout=log, stderr=subprocess.STDOUT, check=True)
        tested = json.loads((trial / "pilot.json").read_bytes())
        if (tested["archive"] != key or tested["provider"] != row["provider"]
                or tested["reexporting_modules"] != modules or tested["parent_sources_sha256"] != row["parent_sources_sha256"]
                or tested["control_sha256"] != row["control_sha256"] or tested["control_binary_sha256"] != row["control_binary_sha256"]
                or tested["raw_pointer_types_removed"] != fields * len(modules)
                or tested["candidate_sha256"] != digest(trial / Path(key).name)):
            raise ValueError(f"unexpected cold-build result in {trial}")
        match = tested["candidate_sha256"] == row["control_sha256"]
        print(f"{trial.name}: {len(modules)} modules, identical={match}", flush=True)
        return match, tested["candidate_sha256"]
    accepted, trace = search(row["reexporting_modules"], limit, compare)
    chosen = next((f"trial-{n:02d}" for n, r in enumerate(trace, 1) if r["identical"] and r["modules"] == accepted), None)
    if chosen and kind == "va-list":
        verify(link, out / chosen, kind)
    result = dict(archive=key, control_sha256=row["control_sha256"], parent_sources_sha256=row["parent_sources_sha256"],
                  whole_candidate_sha256=row["candidate_sha256"], verified_directory=chosen, raw_pointer_types_removed=fields * len(accepted),
                  remaining_modules=sorted(set(row["reexporting_modules"]) - set(accepted)), trials=trace)
    (out / "results.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path)
    parser.add_argument("whole", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--limit", type=int, default=8, help="maximum additional cold-build comparisons")
    parser.add_argument("--kind", choices=("stdio", "va-list"), default="stdio")
    parser.add_argument("--trial", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--modules", nargs="+", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    if args.trial:
        key = json.loads((args.whole / "pilot.json").read_bytes())["archive"]
        if args.kind == "va-list":
            from build_va_list_layout_pilot import build
            build(args.link, key, args.output.resolve(), args.modules)
        else:
            from build_shared_stdio_pilot import build
            build(args.link, args.output.resolve(), Path(key), args.modules)
    else:
        recover(args.link.resolve(), args.whole.resolve(), args.output.resolve(), args.limit, args.kind)
