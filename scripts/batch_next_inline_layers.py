#!/usr/bin/env python3
"""Check newly unreferenced helpers in independent release archives and retain each result."""
# SPDX-License-Identifier: 0BSD
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from check_cargo_private_inlines import ROOT, digest
from check_next_inline_layer import rank


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link_report", type=Path)
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--grouped", action="store_true", help="select Cargo archives from multi-engine packages")
    parser.add_argument("--limit", type=int, help="build the highest-ranked N candidates")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    source = args.link_report.resolve()
    release = json.loads(source.read_bytes())
    candidates = [row for row in rank(release, grouped=args.grouped) if row["estimated_new_leaves"]]
    candidates = candidates[:args.limit]
    directory = Path(tempfile.mkdtemp(prefix="second-layer-batch-", dir=ROOT / "work/analysis"))
    print(f"{len(candidates)} archives, logs in {directory}", flush=True)
    results = {"link_sha256": digest(source),
               "archives": {r["archive"]: {"status": "pending"} for r in candidates}}
    pending = directory / "results.tmp"

    def save():
        pending.write_text(json.dumps(results, sort_keys=True, indent=2) + "\n")
        pending.replace(directory / "results.json")

    save()

    def verify(archive):
        package = Path(archive).parts[2]
        if args.grouped:
            package += "-" + Path(archive).stem
        result = directory / f"{package}.json"
        with (directory / f"{package}.log").open("wb") as log:
            run = subprocess.run([sys.executable, "-B", ROOT / "scripts/check_next_inline_layer.py",
                                  source, archive, result, "--publish"], stdout=log, stderr=subprocess.STDOUT)
        if run.returncode:
            return {"status": "failed", "exit_code": run.returncode}
        record = json.loads(result.read_bytes())
        helpers = record["private_functions_removed"]
        entry = {"status": "verified", "helpers": helpers, "pointers": record["raw_pointer_type_tokens_removed"]}
        if helpers:
            sha = digest(result)
            path = (ROOT / archive).with_suffix(f".layer2-{sha}.json")
            if digest(path) != sha:
                raise ValueError(f"issued receipt differs for {archive}")
            entry["receipt"] = {"file": path.name, "sha256": sha}
        return entry

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(verify, row["archive"]): row["archive"] for row in candidates}
        for task in as_completed(futures):
            archive = futures[task]
            try:
                entry = task.result()
            except (OSError, ValueError, KeyError) as exc:
                entry = {"status": "failed", "error": str(exc)}
            results["archives"][archive] = entry
            print(Path(archive).parts[2], entry["status"], entry.get("pointers", ""), flush=True)
            save()
    return int(any(r["status"] != "verified" for r in results["archives"].values()))


if __name__ == "__main__":
    raise SystemExit(main())
