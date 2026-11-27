#!/usr/bin/env python3
"""Select the strongest verified ABI-sharing result per archive across the narrow and broad sweeps."""
# SPDX-License-Identifier: 0BSD
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from build_scalar_ffi import check_extension
from build_va_list_layout_batch import archive_folder
from check_cargo_private_inlines import digest
from prepare_identical_archives import enroll


def select(link, ranking, narrow, broad, manifest, summary):
    inventory = json.loads(ranking.read_bytes())
    results = [json.loads((p / "results.json").read_bytes()) for p in (narrow, broad)]
    if any(r["link_sha256"] != digest(link) or r["ranking_sha256"] != digest(ranking) for r in results):
        raise ValueError("sweeps must use the same link and syntax ranking")
    broad_state = results[1]
    categories = ("identical", "changed", "errors", "empty", "at_maximum")
    inspected = [key for category in categories for key in broad_state.get(category, {})]
    if len(set(inspected)) != len(inspected) or set(inspected) != inventory["archives"].keys():
        raise ValueError("the broad sweep has no unique result for every ranked archive")
    choices = {}
    for folder, state in zip((narrow, broad), results):
        for key, entry in state["identical"].items():
            pilot = archive_folder(folder, key)
            receipt = pilot / "pilot.json"
            row = json.loads(receipt.read_bytes())
            if (row["archive"] != key or row["candidate_sha256"] != row["control_sha256"]
                    or row["raw_pointer_types_removed"] != entry["raw_pointer_types_removed"]
                    or digest(receipt) != entry["receipt_sha256"]):
                raise ValueError("completed sweep receipt changed")
            if key in choices:
                previous = choices[key][1]
                if row["raw_pointer_types_removed"] <= previous["raw_pointer_types_removed"]:
                    continue
                check_extension(previous, row)
            choices[key] = (pilot, row)
    for key, entry in broad_state.get("at_maximum", {}).items():
        if key not in choices or entry != results[0]["identical"].get(key) or entry["raw_pointer_types_removed"] != inventory["archives"][key]:
            raise ValueError("skipped archive has no verified maximum")
    enroll(link, manifest, [folder for folder, _ in choices.values()], "shared_scalar_ffi")
    totals = {k:row["raw_pointer_types_removed"] for k,(_,row) in choices.items()}
    proof = dict(link_sha256=digest(link), ranking_sha256=digest(ranking), manifest_sha256=digest(manifest),
                 narrow_results_sha256=digest(narrow/"results.json"), broad_results_sha256=digest(broad/"results.json"),
                 ranked=len(inspected), already_at_maximum=len(broad_state.get("at_maximum",{})),
                 accepted=totals, raw_pointer_types_removed=sum(totals.values()),
                 build_errors={key:broad_state["errors"][key] for key in sorted(broad_state["errors"])})
    with TemporaryDirectory(dir=summary.parent) as tmp:
        staged = Path(tmp)/"summary.json"
        staged.write_text(json.dumps(proof, indent=2, sort_keys=True)+"\n")
        staged.replace(summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("link", "ranking", "narrow", "broad", "manifest", "summary"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    select(args.link,args.ranking,args.narrow,args.broad,args.manifest,args.summary)
