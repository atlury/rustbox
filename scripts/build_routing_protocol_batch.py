#!/usr/bin/env python3
"""Cold-build, source-check and compare the routing protocol readers in all selected engines."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import fcntl
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys

from build_routing_protocol_pilot import build
from check_cargo_private_inlines import ROOT, digest
from rank_routing_protocols import rank


def expected_profiles(baseline, public_ip):
    profiles = [dict(profile) for profile in baseline["profiles"]]
    if not public_ip:
        for profile in profiles:
            profile.update(public_successes=0, public_ip_commands=0)
    return profiles


def run(link, output, jobs, engine=None):
    ranking = rank(link)
    selected = ranking["engines"]
    if engine is not None:
        selected = {key: row for key, row in selected.items() if Path(key).name == f"lib{engine}_audit.a"}
        if len(selected) != 1:
            raise ValueError(f"unknown routing protocol engine {engine!r}")
    baseline = json.loads((ROOT / "evidence/iproute2-routing-protocol-pilot.json").read_bytes())
    output.mkdir(exist_ok=True)
    def check_archive(key, predicted, archive, folder):
        if not folder.exists():
            build(link, folder, key)
        row = json.loads((folder / "pilot.json").read_bytes())
        if (row["archive"] != key or row["control_sha256"] != predicted["control_archive_sha256"]
                or any(row[k] != value for k, value in predicted.items() if k != "control_archive_sha256")
                or row["control_binary_sha256"] != ranking["binary_sha256"]
                or digest(ROOT / key) != row["control_sha256"] or digest(folder / archive.name) != row["candidate_sha256"]):
            raise ValueError(f"cold build differs from source replay for {archive}")
        receipt = folder / "comparison.json"
        if not receipt.exists():
            result = subprocess.check_output([sys.executable, "-B", ROOT / "scripts/test_routing_protocol_pilot.py",
                                              folder, link])
        else:
            result = receipt.read_bytes()
        compared = json.loads(result)
        profiles = expected_profiles(baseline, archive.name == "libip_audit.a")
        if (any(compared.get(k) != v for k, v in row.items()) or compared["profiles"] != profiles
                or any(compared.get(k) != baseline[k] for k in ("memcheck_runs", "canonical_source_sha256",
                                                                 "lookup_driver_sha256", "oracle_compilers"))):
            raise ValueError(f"incomplete or different canonical observations for {archive}")
        if not receipt.exists():
            pending = folder / "comparison.json.tmp"
            pending.write_bytes(result)
            pending.replace(receipt)
        print(f"{archive.name}: {row['raw_pointer_types_removed']} pointer types, four canonical profiles passed", flush=True)
        return key, compared
    def test(item):
        key, predicted = item
        archive = Path(key)
        with (output / (archive.stem + ".lock")).open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            return check_archive(key, predicted, archive, output / archive.stem)

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        checked = dict(pool.map(test, sorted(selected.items())))
    if digest(link) != ranking["link_report_sha256"]:
        raise ValueError("release changed during archive comparisons")
    totals = dict(verified=checked, binary_sha256=ranking["binary_sha256"], link_report_sha256=ranking["link_report_sha256"],
                  raw_pointer_types_removed=sum(r["raw_pointer_types_removed"] for r in checked.values()),
                  canonical_lookups=sum(p["forward"]+p["reverse"] for r in checked.values() for p in r["profiles"]),
                  public_ip_commands=sum(p["public_ip_commands"] for r in checked.values() for p in r["profiles"]),
                  memcheck_runs=sum(r["memcheck_runs"] for r in checked.values()))
    destination = output / ("results.json" if engine is None else f"{engine}-results.json")
    pending = destination.with_suffix(".json.tmp")
    pending.write_text(json.dumps(totals, indent=2, sort_keys=True)+"\n")
    pending.replace(destination)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("link", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--engine", help="qualify a single engine and save its own result")
    p.add_argument("--jobs", type=int, default=2)
    args = p.parse_args()
    if args.jobs < 1:
        p.error("--jobs must be positive")
    run(args.link.resolve(), args.output.resolve(), args.jobs, args.engine)
