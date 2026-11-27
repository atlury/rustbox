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


def archive_folder(output, key):
    return output / (Path(key).stem + "-" + sha256(key.encode()).hexdigest()[:12])


def recover_changed(link, sweep, output, packages, limit, manifest=None):
    from recover_shared_stdio import recover
    source = sweep / "results.json"
    proof = json.loads(source.read_bytes())
    if digest(link) != proof["link_report_sha256"] or proof["errors"]:
        raise ValueError("expected a complete archive sweep for this link report")
    selected = {k: v for k, v in proof["changed"].items() if not packages or Path(k).parts[2] in packages}
    if not selected or set(packages) - {Path(k).parts[2] for k in selected}:
        raise ValueError("no changed archive for the selected package")
    output.mkdir(exist_ok=True)
    accepted = []
    # Try the highest potential savings first. Each archive has its own resumable trials.
    for key, row in sorted(selected.items(), key=lambda item: (-item[1]["raw_pointer_types_removed"], item[0])):
        whole = archive_folder(sweep, key)
        if json.loads((whole / "pilot.json").read_bytes()) != row:
            raise ValueError(f"whole-archive compiler receipt changed for {key}")
        folder = archive_folder(output, key)
        with folder.with_name(folder.name + ".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            recover(link, whole, folder, limit, "va-list")
            result = json.loads((folder / "results.json").read_bytes())
            if result["verified_directory"]:
                accepted.append(folder / result["verified_directory"])
            print(f"{Path(key).name}: {result['raw_pointer_types_removed']} fields recovered", flush=True)
    if digest(link) != proof["link_report_sha256"]:
        raise ValueError("linked source release changed during recovery")
    if manifest is not None:
        if not accepted:
            raise ValueError("no byte-identical subset qualified for the requested manifest")
        from prepare_identical_archives import enroll
        enroll(link, manifest, accepted, "shared_va_list_layouts")


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
        folder = archive_folder(output, key)
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
    p.add_argument("--recover-from", type=Path, help="recover changed archives from a completed sweep into a separate output")
    p.add_argument("--manifest", type=Path, help="enroll the recovered byte-identical subsets in an optional link manifest")
    p.add_argument("--trials", type=int, help="maximum cumulative subset comparisons per changed archive (default 4)")
    args = p.parse_args()
    if args.recover_from:
        if args.trials is not None and args.trials < 1:
            p.error("--trials must be positive")
        if args.output.resolve() == args.recover_from.resolve():
            p.error("subset results need a separate directory")
        recover_changed(args.link.resolve(), args.recover_from.resolve(), args.output.resolve(), args.package, args.trials or 4, args.manifest)
        raise SystemExit(0)
    if args.trials is not None or args.manifest is not None:
        p.error("--trials and --manifest require --recover-from")
    if args.jobs < 1:
        p.error("jobs must be positive")
    raise SystemExit(run(args.link.resolve(), args.output.resolve(), args.package, args.jobs))
