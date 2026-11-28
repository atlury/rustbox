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

from check_cargo_private_inlines import ROOT, digest
from rank_routing_protocols import rank


def expected_profiles(baseline, public_ip, *, dsfield=False, group_names=False):
    profiles = [dict(profile) for profile in baseline["profiles"]]
    if not public_ip:
        for profile in profiles:
            if group_names:
                profile["public_statuses"] = []
            elif dsfield:
                profile["public_filter_status"] = []
            else:
                profile.update(public_successes=0, public_ip_commands=0)
    return profiles


def run(link, output, jobs, engine=None, *, dsfield=False, group_names=False):
    if group_names:
        from build_group_names import build
        evidence_name = "iproute2-group-names-pilot.json"
        driver = "test_group_names.py"
        qualification = ("memcheck_runs", "canonical_sha256", "driver_sha256", "oracle_compilers", "helper_sha256")
    elif dsfield:
        from build_dsfield_names import build
        evidence_name = "iproute2-dsfield-pilot.json"
        driver = "test_dsfield_names.py"
        qualification = ("memcheck_runs", "canonical_inputs", "driver_sha256", "oracle_compilers")
    else:
        from build_routing_protocol_pilot import build
        evidence_name = "iproute2-routing-protocol-pilot.json"
        driver = "test_routing_protocol_pilot.py"
        qualification = ("memcheck_runs", "canonical_source_sha256", "lookup_driver_sha256", "oracle_compilers")
    ranking = rank(link, dsfield=dsfield, group_names=group_names)
    selected = ranking["engines"]
    if group_names:
        from cargo_source_parent import cargo_origin, direct_crate
        parent = json.loads(link.read_bytes())
        deferred_direct = sorted(k for k in selected if direct_crate(cargo_origin(parent, k)) is not None)
        selected = {k:v for k,v in selected.items() if k not in deferred_direct}
    if engine is not None:
        selected = {key: row for key, row in selected.items() if Path(key).name == f"lib{engine}_audit.a"}
        if len(selected) != 1:
            raise ValueError(f"unknown routing protocol engine {engine!r}")
    baseline = json.loads((ROOT / "evidence" / evidence_name).read_bytes())
    output.mkdir(exist_ok=True)
    def check_archive(key, predicted, archive, folder):
        if not folder.exists():
            build(link, folder, key)
        row = json.loads((folder / "pilot.json").read_bytes())
        if (row["archive"] != key or row["control_sha256"] != predicted["control_archive_sha256"]
                or any(row[k] != value for k, value in predicted.items() if k not in ("control_archive_sha256", "with_dsfield_module_sha256"))
                or row["control_binary_sha256"] != ranking["binary_sha256"]
                or digest(ROOT / key) != row["control_sha256"] or digest(folder / archive.name) != row["candidate_sha256"]):
            raise ValueError(f"cold build differs from source replay for {archive}")
        receipt = folder / "comparison.json"
        if not receipt.exists():
            arguments = ["--pilot", folder, "--link", link] if group_names else [folder, link]
            result = subprocess.check_output([sys.executable, "-B", ROOT / "scripts" / driver, *arguments])
        else:
            result = receipt.read_bytes()
        compared = json.loads(result)
        profiles = expected_profiles(baseline, archive.name == "libip_audit.a", dsfield=dsfield, group_names=group_names)
        if (dsfield or group_names) and compared.get("public_oracle_sha256") != (baseline["public_oracle_sha256"] if archive.name == "libip_audit.a" else {}):
            raise ValueError(f"canonical ip filter binaries differ for {archive}")
        if (any(compared.get(k) != v for k, v in row.items()) or compared["profiles"] != profiles
                or any(compared.get(k) != baseline[k] for k in qualification)):
            raise ValueError(f"incomplete or different canonical observations for {archive}")
        if not receipt.exists():
            pending = folder / "comparison.json.tmp"
            pending.write_bytes(result)
            pending.replace(receipt)
        print(f"{archive.name}: {row['raw_pointer_types_removed']} pointer types, {len(profiles)} canonical profiles passed", flush=True)
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
    profiles = [p for row in checked.values() for p in row["profiles"]]
    if group_names:
        lookups = sum(p["forward"] + p["reverse"] for p in profiles)
        commands = sum(len(p["public_statuses"]) for p in profiles)
    elif dsfield:
        lookups = sum(sum(p["counts"].values()) for p in profiles)
        commands = sum(len(p["public_filter_status"]) for p in profiles)
    else:
        lookups = sum(p["forward"] + p["reverse"] for p in profiles)
        commands = sum(p["public_ip_commands"] for p in profiles)
    totals = dict(verified=checked, binary_sha256=ranking["binary_sha256"], link_report_sha256=ranking["link_report_sha256"],
                  raw_pointer_types_removed=sum(r["raw_pointer_types_removed"] for r in checked.values()),
                  canonical_lookups=lookups, public_ip_commands=commands,
                  memcheck_runs=sum(r["memcheck_runs"] for r in checked.values()))
    if group_names:
        totals["direct_engines_pending"] = deferred_direct
    batch_name = "cargo-results.json" if group_names else "results.json"
    destination = output / (batch_name if engine is None else f"{engine}-results.json")
    pending = destination.with_suffix(".json.tmp")
    pending.write_text(json.dumps(totals, indent=2, sort_keys=True)+"\n")
    pending.replace(destination)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("link", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--engine", help="qualify a single engine and save its own result")
    p.add_argument("--jobs", type=int, default=2)
    choice = p.add_mutually_exclusive_group()
    choice.add_argument("--group-names", action="store_true", help="qualify device group lookups in the Cargo engines")
    choice.add_argument("--dsfield", action="store_true", help="qualify the DS field and DSCP reader on the routing parent")
    args = p.parse_args()
    if args.jobs < 1:
        p.error("--jobs must be positive")
    run(args.link.resolve(), args.output.resolve(), args.jobs, args.engine, dsfield=args.dsfield, group_names=args.group_names)
