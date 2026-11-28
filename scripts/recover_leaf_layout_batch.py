#!/usr/bin/env python3
"""Recover additional byte-identical groups from completed Cargo and direct-rustc layout batches."""
# SPDX-License-Identifier: 0BSD
import argparse
import fcntl
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from build_va_list_layout_batch import archive_folder
from check_cargo_private_inlines import digest
from recover_leaf_layouts import recover


def run(link, ranking, batches, output, limit):
    if limit < 1 or not batches or output.resolve() in {p.resolve() for p in batches}:
        raise ValueError("expected source batches, separate output and a positive trial limit")
    parent = json.loads(link.read_bytes())
    report = dict(link_sha256=digest(link), ranking_sha256=digest(ranking), batches={}, additional={},
                  primary_pointer_types_removed=0, recovered_pointer_types_removed=0, skipped_single_layouts=[], primary_errors={})
    trials = {}
    seen = set()
    for batch in batches:
        snapshot = batch / "results.json"
        with (batch / "batch.lock").open("r") as lock:
            fcntl.flock(lock, fcntl.LOCK_SH)
            raw = json.loads(snapshot.read_bytes())
            if (raw["link_sha256"] != report["link_sha256"] or raw["ranking_sha256"] != report["ranking_sha256"]
                    or raw["selected"] != sum(len(raw[k]) for k in ("identical", "changed", "errors"))):
                raise ValueError("a source batch is incomplete or belongs to a different release")
            report["batches"][str(batch)] = digest(snapshot)
            keys = set(raw["identical"]) | set(raw["changed"]) | set(raw["errors"])
            if len(keys) != raw["selected"] or seen.intersection(keys):
                raise ValueError("archives overlap across batch results")
            seen.update(keys)
            total = sum(item["raw_pointer_types_removed"] for item in raw["identical"].values())
            if total != raw["verified_pointer_types_removed"]:
                raise ValueError("inconsistent primary pointer reduction")
            report["primary_pointer_types_removed"] += total
            report["primary_errors"].update(raw["errors"])
            for key, row in (raw["identical"] | raw["changed"]).items():
                folder = archive_folder(batch, key)
                if digest(folder / "pilot.json") != row["pilot_sha256"]:
                    raise ValueError(f"archive receipt differs from the batch for {key}")
                pilot = json.loads((folder / "pilot.json").read_bytes())
                if (pilot["archive"] != key or pilot["control_binary_sha256"] != parent["binary"]["sha256"]
                        or parent["source_library_sha256"].get(key) != pilot["control_sha256"]
                        or row["archive_sha256"] != pilot["candidate_sha256"]
                        or row["raw_pointer_types_removed"] != pilot["raw_pointer_types_removed"]
                        or row["layouts"] != sorted(pilot["leaf_layouts"])
                        or (key in raw["identical"]) != (pilot["control_sha256"] == pilot["candidate_sha256"])):
                    raise ValueError(f"source batch and compiler receipt disagree for {key}")
                if key in raw["identical"]:
                    continue
                if len(row["layouts"]) == 1:
                    report["skipped_single_layouts"].append(key)
                else:
                    trials[key] = folder, row["raw_pointer_types_removed"]

    output.mkdir(exist_ok=True, parents=True)
    with (output / "batch.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for key in sorted(trials, key=lambda k: (-trials[k][1], k)):
            folder, maximum = trials[key]
            dest = archive_folder(output, key)
            result = recover(link, ranking, folder, dest, limit)
            n = result["raw_pointer_types_removed"]
            if not 0 <= n < maximum:
                raise ValueError("expected a strict subset of a differing whole-archive selection")
            report["additional"][key] = dict(raw_pointer_types_removed=n, accepted=result["accepted"],
                                             whole_receipt_sha256=result["whole_receipt_sha256"],
                                             recovery_sha256=digest(dest / "results.json"))
            report["recovered_pointer_types_removed"] += n
            print(Path(key).name, n, report["recovered_pointer_types_removed"], flush=True)
        if (report["link_sha256"] != digest(link) or report["ranking_sha256"] != digest(ranking)
                or any(digest(Path(batch) / "results.json") != checksum for batch, checksum in report["batches"].items())):
            raise ValueError("source batch or release changed during recovery")
        with NamedTemporaryFile(mode="w", dir=output, delete=False) as staged:
            json.dump(report, staged, indent=2, sort_keys=True)
            staged.write("\n")
        Path(staged.name).replace(output / "results.json")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("link", type=Path)
    p.add_argument("ranking", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("batches", type=Path, nargs="+")
    p.add_argument("--limit", type=int, default=8, help="maximum additional cold builds per differing archive")
    args = p.parse_args()
    if args.limit < 1:
        p.error("--limit must be positive")
    run(args.link, args.ranking, args.batches, args.output, args.limit)
