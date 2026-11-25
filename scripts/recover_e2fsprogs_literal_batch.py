#!/usr/bin/env python3
"""Test the best known peer module selection in each E2fsprogs archive that differed in the full sweep."""
# SPDX-License-Identifier: GPL-2.0-only
import argparse
import fcntl
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from check_cargo_private_inlines import digest
from recover_e2fsprogs_literal_modules import PACKAGE, recover


def run(link, batch, seed, output, engines):
    original = digest(link)
    report = json.loads((batch / "results.json").read_bytes())
    example = json.loads((seed / "pilot.json").read_bytes())
    if report["link_report_sha256"] != original or example["candidate_sha256"] != example["control_sha256"]:
        raise ValueError("expected a qualified seed and the same batch parent")
    targets = {Path(k).name.removeprefix("lib").removesuffix("_audit.a"): k for k, why in report["deferred"].items()
               if Path(k).parts[2] == PACKAGE and why == "rebuilt archive bytes differ" and k != example["archive"]}
    if set(engines) - targets.keys() or not targets:
        raise ValueError("requested engine lacks a differing whole-archive build")
    output.mkdir(exist_ok=True)
    selected = sorted(set(engines) or targets)
    result = dict(link_report_sha256=original, seed_receipt_sha256=digest(seed / "pilot.json"),
                  peer_batch_sha256=digest(batch / "results.json"), identical={}, changed={})
    for engine in selected:
        target = output / engine
        with (output / (engine + ".lock")).open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            recover(link, batch, target, engine, seed=seed)
            compared = json.loads((target / "comparison.json").read_bytes())
            row = compared["candidate"]
            if compared["seed_receipt_sha256"] != result["seed_receipt_sha256"] or row["archive"] != targets[engine]:
                raise ValueError("unexpected peer substitution")
            category = "identical" if compared["byte_identical"] else "changed"
            result[category][row["archive"]] = row
    if original != digest(link) or result["seed_receipt_sha256"] != digest(seed / "pilot.json"):
        raise ValueError("parent or seed changed during recovery")
    result["raw_pointer_types_removed"] = sum(r["raw_pointer_types_removed"] for r in result["identical"].values())
    outfile = "results.json" if not engines else "results-" + "-".join(selected) + ".json"
    with TemporaryDirectory(dir=output) as tmp:
        pending = Path(tmp) / outfile
        pending.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        pending.replace(output / outfile)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("link", "batch", "seed", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--engine", action="append", default=[])
    args = parser.parse_args()
    run(args.link, args.batch, args.seed, args.output, args.engine)
