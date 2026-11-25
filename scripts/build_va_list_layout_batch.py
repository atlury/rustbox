#!/usr/bin/env python3
"""Build and replay repeated x86-64 variadic layouts across the selected Cargo and direct-rustc archives."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from build_va_list_layout_pilot import TAG
from check_cargo_private_inlines import ROOT, digest
from rank_leaf_c_layouts import leaf_layouts, rank
from verify_shared_layout_sources import verify


def run(link, output, packages, jobs):
    inventory = rank(link, None)
    name, fingerprint, fields = leaf_layouts(TAG)[0]
    group, = [g for g in inventory["layouts"] if (g["name"], g["declaration_and_field_types_sha256"]) == (name, fingerprint)]
    selection = {k: v for k, v in group["archives"].items() if not packages or Path(k).parts[2] in packages}
    if not selection or set(packages) - {Path(k).parts[2] for k in selection}:
        raise ValueError("package selection contains no matching duplicate layout")
    output.mkdir(exist_ok=True)

    def inspect(item):
        key, copies = item
        folder = output / (Path(key).stem + "-" + sha256(key.encode()).hexdigest()[:12])
        with folder.with_name(folder.name + ".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not folder.exists():
                log = folder.with_name(folder.name + ".log")
                with log.open("wb") as stream:
                    process = subprocess.run([sys.executable, "-B", ROOT/"scripts/build_va_list_layout_pilot.py",
                                              "--link", link, "--archive", key, "--output", folder],
                                             stdout=stream, stderr=subprocess.STDOUT)
                if process.returncode:
                    print(f"{Path(key).name}: compiler exited {process.returncode}, see {log.name}", flush=True)
                    return key, "errors", dict(status=process.returncode, log=log.name)
            try:
                verify(link, folder, "va-list")
                row = json.loads((folder / "pilot.json").read_bytes())
                if (row["archive"] != key or row["raw_pointer_types_removed"] != fields * (copies - 1)
                        or len(row["reexporting_modules"]) + 1 != copies):
                    raise ValueError("compiler inputs differ from the ranked variadic declarations")
            except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
                print(f"{Path(key).name}: source replay failed: {error}", flush=True)
                return key, "errors", dict(stage="source replay", error=str(error))
            category = "identical" if row["candidate_sha256"] == row["control_sha256"] else "changed"
            print(f"{Path(key).name}: {row['raw_pointer_types_removed']} repeated fields, archive {category}", flush=True)
            return key, category, row

    result = dict(link_report_sha256=inventory["link_report_sha256"], binary_sha256=inventory["binary_sha256"],
                  identical={}, changed={}, errors={})
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        for key, category, row in pool.map(inspect, sorted(selection.items(), key=lambda pair: (pair[1], pair[0]))):
            result[category][key] = row
    if digest(link) != inventory["link_report_sha256"]:
        raise ValueError("source release changed during the variadic layout sweep")
    result["identical_pointer_types_removed"] = sum(r["raw_pointer_types_removed"] for r in result["identical"].values())
    with TemporaryDirectory(dir=output) as tmp:
        receipt = Path(tmp) / "results.json"
        receipt.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        receipt.replace(output / "results.json")
    return bool(result["errors"])


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("link", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--package", action="append", default=[])
    p.add_argument("--jobs", type=int, default=2)
    args = p.parse_args()
    if args.jobs < 1:
        p.error("jobs must be positive")
    raise SystemExit(run(args.link.resolve(), args.output.resolve(), args.package, args.jobs))
