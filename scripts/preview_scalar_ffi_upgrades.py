#!/usr/bin/env python3
"""Find scalar declaration upgrades on the current compiler inputs before cold rebuilding."""
# SPDX-License-Identifier: 0BSD
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

from build_checked_errno import replay
from build_scalar_ffi import SOURCE, substitute
from cargo_source_parent import archives_by_origin, row_origin
from check_cargo_private_inlines import digest
from prepare_identical_archives import selected_receipts
from verify_c_string_sources import syntax_tool

FIELD = "shared_scalar_ffi"
LATER = ("shared_variadic_ffi", "shared_leaf_layouts")


def preview(link, selected, historical, jobs):
    if jobs < 1:
        raise ValueError("expected at least one worker")
    inputs = {p: digest(p) for p in (link, selected, historical, SOURCE)}
    parent, current, previous = (json.loads(p.read_bytes()) for p in (link, selected, historical))
    if any(field in parent for field in (FIELD, *LATER)):
        raise ValueError("expected the link immediately preceding scalar declaration sharing")
    stripped = {k: v for k, v in current.items() if k not in (FIELD, *LATER)}
    if stripped != parent:
        raise ValueError("the selected release and scalar parent have different compiler inputs")

    origins = archives_by_origin(parent)
    candidates = set()
    for old, item in previous.items():
        row = item["pilot"]
        if row["archive"] != old or row["control_sha256"] != row["candidate_sha256"]:
            raise ValueError(f"historical archive receipt differs for {old}")
        key = origins.get(row_origin(row))
        if (key and row.get("all_scalar_interfaces")
                and not current.get(FIELD, {}).get(key, {}).get("all_scalar_interfaces")):
            candidates.add(key)

    tool = syntax_tool("scalar-ffi")
    def inspect(key):
        row = replay(link, key, transform=lambda crate, sources: substitute(crate, sources, tool, all_interfaces=True))
        if row["control_sha256"] != parent["source_library_sha256"][key]:
            raise ValueError(f"linked archive changed for {key}")
        installed = current.get(FIELD, {}).get(key)
        if installed and (installed["parent_sources_sha256"] != row["parent_sources_sha256"]
                          or any(row["scalar_ffi"].get(k) != v for k, v in installed["scalar_ffi"].items())):
            raise ValueError(f"existing scalar selection differs for {key}")
        scalar = installed["raw_pointer_types_removed"] if installed else 0
        displaced = {layer: current[layer][key]["raw_pointer_types_removed"]
                     for layer in LATER if key in current.get(layer, {})}
        return key, dict(control_archive_sha256=row["control_sha256"], compiler_sources=row["compiler_selected_sources"],
                         parent_sources_sha256=row["parent_sources_sha256"], candidate_sources_sha256=row["candidate_sources_sha256"],
                         parent_layers=sorted(selected_receipts(parent, key, FIELD)), selected_scalar=scalar,
                         proposed_scalar=row["raw_pointer_types_removed"], displaced_later_layers=displaced,
                         net_if_replaced=row["raw_pointer_types_removed"] - scalar - sum(displaced.values()))

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        rows = dict(pool.map(inspect, sorted(candidates)))
    if any(digest(p) != checksum for p, checksum in inputs.items()):
        raise ValueError("compiler inputs or scanner changed during source replay")
    return dict(link_sha256=inputs[link], selected_sha256=inputs[selected], historical_manifest_sha256=inputs[historical],
                scanner_sha256=inputs[SOURCE], binary_sha256=parent["binary"]["sha256"], archives=rows,
                positive_net_if_replaced=sum(max(0, r["net_if_replaced"]) for r in rows.values()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("link", "selected", "historical"):
        parser.add_argument(arg, type=Path)
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    print(json.dumps(preview(args.link, args.selected, args.historical, args.jobs), indent=2, sort_keys=True))
