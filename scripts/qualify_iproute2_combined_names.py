#!/usr/bin/env python3
"""Build the two owned IPRoute2 name readers together and compare each selected engine with both C oracles."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import fcntl
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from build_group_names import build
from check_cargo_private_inlines import digest
from link_rustbox_multicall import IPROUTE2_PROGRAMS
from stage_dsfield_archives import FIELD, candidate_path, parent_view
from test_iproute2_combined_names import check


def write_result(path, result):
    with NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write("\n")
    Path(stream.name).replace(path)


def qualify(link, output):
    release = json.loads(link.read_bytes())
    original = digest(link)
    parent_view(release)
    wanted = {f"lib{engine}_audit.a" for engine in IPROUTE2_PROGRAMS}
    selected = sorted(candidate_path(row) for row in release[FIELD].values())
    if len(selected) != len(wanted) or {p.name for p in selected} != wanted:
        raise ValueError("expected one DS field archive for each IPRoute2 engine")
    output.mkdir(exist_ok=True)
    results = {}
    for path in selected:
        directory = output / path.stem
        with (output / (path.stem + ".lock")).open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not directory.exists():
                build(link, directory, str(path))
            # Each invocation reuses a completed cold build and exercises both interfaces.
            checked = check(link, directory)
            if checked["link_sha256"] != original or checked["archive"]["archive"] != str(path):
                raise ValueError(f"source release changed while testing {path}")
            write_result(directory / "combined-comparison.json", checked)
            results[str(path)] = checked
            print(f"{path.name} passed both canonical lookup suites", flush=True)
    groups = [profile for row in results.values() for profile in row["comparisons"]["group"]["profiles"]]
    fields = [profile for row in results.values() for profile in row["comparisons"]["dsfield"]["profiles"]]
    summary = dict(verified=results, link_sha256=original, binary_sha256=release["binary"]["sha256"],
                   raw_pointer_types_removed=sum(r["raw_pointer_types_removed"] for r in results.values()),
                   group_lookups=sum(p["forward"] + p["reverse"] for p in groups),
                   dsfield_lookups=sum(sum(p["counts"].values()) for p in fields),
                   public_filters=sum(len(p["public_statuses"]) for p in groups) + sum(len(p["public_filter_status"]) for p in fields),
                   memcheck_runs=sum(c["memcheck_runs"] for r in results.values() for c in r["comparisons"].values()))
    if digest(link) != original:
        raise ValueError("parent release changed during comparison")
    write_result(output / "combined-results.json", summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    qualify(args.link, args.output)
