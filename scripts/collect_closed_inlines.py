#!/usr/bin/env python3
"""Enroll jointly verified closed helper groups and report disjoint archive coverage."""
# SPDX-License-Identifier: 0BSD
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from build_va_list_layout_batch import archive_folder
from check_cargo_private_inlines import digest
from prepare_identical_archives import enroll


def collect(link, ranking, batches, manifest, evidence, complete=False, *, scalar_ffi=False):
    inventory = json.loads(ranking.read_bytes())
    from batch_closed_inlines import ranked_inputs
    candidates, source, _, _ = ranked_inputs(inventory, scalar_ffi)
    layer = "shared_scalar_ffi" if scalar_ffi else "closed_inline_groups"
    if digest(source) != inventory["scanner_source_sha256"]:
        raise ValueError("scanner differs from the ranked source")
    rank_sha = digest(ranking)
    if digest(link) != inventory["link_sha256"]:
        raise ValueError("ranking and release differ")
    accepted = []
    outcomes = {}
    totals = {}
    for batch in batches:
        state = json.loads((batch / "results.json").read_bytes())
        if (state["link_sha256"] != inventory["link_sha256"] or state["ranking_sha256"] != rank_sha
                or state["binary_sha256"] != inventory["binary_sha256"]):
            raise ValueError("batch does not belong to the requested release and ranking")
        for category in ("identical", "changed", "empty", "errors"):
            for key, receipt in state.get(category, {}).items():
                if key in outcomes or key not in candidates:
                    raise ValueError("duplicate or unranked engine")
                outcomes[key] = category
                if category != "identical":
                    continue
                directory = archive_folder(batch, key)
                source = directory / "pilot.json"
                row = json.loads(source.read_bytes())
                if (bool(row.get("all_scalar_interfaces")) != (scalar_ffi == "all")
                        or digest(source) != receipt["receipt_sha256"] or row["archive"] != key
                        or {k: v for k, v in row.items() if k != "dead_sites"}
                            != {k: v for k, v in receipt.items() if k != "receipt_sha256"}):
                    raise ValueError("verified batch receipt changed")
                accepted.append(directory)
                totals[key] = {k: row[k] for k in ("raw_pointer_types_removed", "candidate_sha256")}
                if not scalar_ffi:
                    totals[key]["private_helpers_removed"] = row["private_helpers_removed"]
    if complete and (set(outcomes) != candidates.keys() or "errors" in outcomes.values()):
        raise ValueError("complete collection requires a verified outcome for every ranked archive")
    if not accepted:
        raise ValueError("no byte-identical archive has qualified")
    enroll(link, manifest, sorted(accepted), layer)
    result = dict(link_sha256=inventory["link_sha256"], binary_sha256=inventory["binary_sha256"],
                  ranking_sha256=rank_sha, manifest_sha256=digest(manifest), ranked=len(candidates),
                  outcomes=outcomes, identical=totals,
                  raw_pointer_types_removed=sum(row["raw_pointer_types_removed"] for row in totals.values()))
    if not scalar_ffi:
        result["private_helpers_removed"] = sum(row["private_helpers_removed"] for row in totals.values())
    with TemporaryDirectory(dir=evidence.parent) as tmp:
        staged = Path(tmp) / "summary.json"
        staged.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        staged.replace(evidence)
    print(f'{len(accepted)} identical archives, {result["raw_pointer_types_removed"]} verified pointer declarations', flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path)
    parser.add_argument("ranking", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("summary", type=Path)
    parser.add_argument("batches", type=Path, nargs="+")
    parser.add_argument("--complete", action="store_true")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--all-scalar-ffi", action="store_const", const="all", dest="scalar_ffi")
    scope.add_argument("--scalar-ffi", action="store_true")
    args = parser.parse_args()
    collect(args.link, args.ranking, args.batches, args.manifest, args.summary, args.complete, scalar_ffi=args.scalar_ffi)
