#!/usr/bin/env python3
"""Cold-build and independently replay closed private helper groups across ranked archives."""
# SPDX-License-Identifier: 0BSD
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import json
from pathlib import Path
import subprocess
import sys
from tempfile import NamedTemporaryFile

from build_closed_inlines import SOURCE
from build_va_list_layout_batch import archive_folder
from check_cargo_private_inlines import ROOT, digest

EMPTY_DIAGNOSTIC = b"ValueError: these compiler-dead groups contain no raw pointer types"
DRIVER = ROOT / "scripts/build_closed_inlines.py"


def run(link, ranking, output, packages, jobs, exclude=()):
    inventory = json.loads(ranking.read_bytes())
    signature = inventory["link_sha256"]
    if (digest(link) != signature or json.loads(link.read_bytes())["binary"]["sha256"] != inventory["binary_sha256"]
            or digest(SOURCE) != inventory["scanner_source_sha256"]):
        raise ValueError("ranking does not match the selected release and scanner")
    selected = {key: row for key, row in inventory["archives"].items()
                if (not packages or Path(key).parts[2] in packages) and Path(key).parts[2] not in exclude}
    if not selected or set(packages) - {Path(key).parts[2] for key in selected}:
        raise ValueError("unknown or empty package selection")
    output.mkdir(parents=True, exist_ok=True)
    driver = [sys.executable, "-B", DRIVER, "--link", link]

    def inspect(key):
        folder = archive_folder(output, key)
        log = folder.with_suffix(".log")
        with folder.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not folder.exists():
                with log.open("wb") as stream:
                    proc = subprocess.run([*driver, "--archive", key, "--output", folder],
                                          stdout=stream, stderr=subprocess.STDOUT)
                if proc.returncode:
                    with log.open("rb") as stream:
                        if any(line.rstrip() == EMPTY_DIAGNOSTIC for line in stream):
                            return "empty", {"log": log.name, "log_sha256": digest(log)}
                    proc.check_returncode()
            with log.open("ab") as stream:
                subprocess.run([*driver, "--replay", folder], check=True, stdout=stream, stderr=subprocess.STDOUT)
            row = json.loads((folder / "pilot.json").read_bytes())
            if (row["archive"] != key or row["control_binary_sha256"] != inventory["binary_sha256"]
                    or not 0 < row["raw_pointer_types_removed"] <= selected[key]["pointer_types"]):
                raise ValueError("compiler receipt does not match ranked candidate")
            category = "identical" if row["control_sha256"] == row["candidate_sha256"] else "changed"
            return category, {k: v for k, v in row.items() if k != "dead_sites"} | {"receipt_sha256": digest(folder / "pilot.json")}

    result = dict(link_sha256=signature, binary_sha256=inventory["binary_sha256"], ranking_sha256=digest(ranking),
                  selected=len(selected), identical={}, changed={}, empty={}, errors={})
    # Serialize supervisors sharing an output directory. Individual pilots survive interruptions.
    with (output / "batch.lock").open("a") as lock, ThreadPoolExecutor(max_workers=jobs) as pool:
        fcntl.flock(lock, fcntl.LOCK_EX)
        tasks = {pool.submit(inspect, key): key for key in selected}
        for task in as_completed(tasks):
            key = tasks[task]
            try:
                category, row = task.result()
                result[category][key] = row
            except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
                category = "errors"
                result[category][key] = str(exc)
            if digest(link) != signature:
                raise ValueError("release changed during batch")
            result["verified_pointer_types_removed"] = sum(r["raw_pointer_types_removed"] for r in result["identical"].values())
            with NamedTemporaryFile(mode="w", dir=output, delete=False) as tmp:
                json.dump(result, tmp, indent=2, sort_keys=True)
                tmp.write("\n")
            Path(tmp.name).replace(output / "results.json")
            print(Path(key).name, category, result["verified_pointer_types_removed"], flush=True)
    return not result["errors"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path)
    parser.add_argument("ranking", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--package", action="append", default=[])
    parser.add_argument("--exclude-package", action="append", default=[])
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    sys.exit(0 if run(args.link, args.ranking, args.output, args.package, args.jobs, args.exclude_package) else 1)
