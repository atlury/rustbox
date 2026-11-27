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


def collect(link, ranking, batches, manifest, evidence, complete=False):
    inventory = json.loads(ranking.read_bytes())
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
                if key in outcomes or key not in inventory["archives"]:
                    raise ValueError("duplicate or unranked engine")
                outcomes[key] = category
                if category != "identical":
                    continue
                directory = archive_folder(batch, key)
                source = directory / "pilot.json"
                row = json.loads(source.read_bytes())
                if (digest(source) != receipt["receipt_sha256"] or row["archive"] != key
                        or {k: v for k, v in row.items() if k != "dead_sites"}
                            != {k: v for k, v in receipt.items() if k != "receipt_sha256"}):
                    raise ValueError("verified batch receipt changed")
                accepted.append(directory)
                totals[key] = {k: row[k] for k in ("private_helpers_removed", "raw_pointer_types_removed", "candidate_sha256")}
    if complete and (set(outcomes) != inventory["archives"].keys() or "errors" in outcomes.values()):
        raise ValueError("complete collection requires a verified outcome for every ranked archive")
    if not accepted:
        raise ValueError("no byte-identical archive has qualified")
    enroll(link, manifest, sorted(accepted), "closed_inline_groups")
    result = dict(link_sha256=inventory["link_sha256"], binary_sha256=inventory["binary_sha256"],
                  ranking_sha256=rank_sha, manifest_sha256=digest(manifest), ranked=len(inventory["archives"]),
                  outcomes=outcomes, identical=totals,
                  private_helpers_removed=sum(row["private_helpers_removed"] for row in totals.values()),
                  raw_pointer_types_removed=sum(row["raw_pointer_types_removed"] for row in totals.values()))
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
    args = parser.parse_args()
    collect(args.link, args.ranking, args.batches, args.manifest, args.summary, args.complete)
