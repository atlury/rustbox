#!/usr/bin/env python3
"""Reproduce and qualify the linked IPRoute2 archives for each name-table substitution."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys

from build_iproute2_address_protocol_pilot import build_pilot
from build_iproute2_bridge_address_protocols import BRIDGE, build_bridge_trial
from check_cargo_private_inlines import ROOT, digest
from check_e2fsprogs_dirhash_arrays import source_list_digest
from iproute2_address_protocol_archive import candidate_path, control_view, selected_records
from iproute2_route_name_archives import build_control_view, manifest, prepare
from iproute2_route_names import replace_route_names
from stage_iproute2_address_protocols import MODULE, compiler_inputs, replace_table


def check(link, key, output, *, netlink_protocols=False):
    parents = selected_records(link)
    parent = link["iproute2_route_names"][key] if netlink_protocols else parents[key]
    flags = {"netlink_protocols": True} if netlink_protocols else {"route_names": True}
    name = Path(key).stem.removeprefix("lib").removesuffix("_audit")
    if not output.exists():
        if Path(key) == BRIDGE:
            build_bridge_trial(output, link, **flags)
        else:
            build_pilot(output, link, name, **flags)
    control, files = compiler_inputs(control_view(link), key)
    module, _ = replace_table(control)
    module, changes = replace_route_names(module)
    archive_path = candidate_path
    if netlink_protocols:
        from iproute2_route_names import replace_netlink_protocols
        from iproute2_route_name_archives import candidate_path as archive_path
        _, changes = replace_netlink_protocols(module)
    files = {str(k): v for k, v in files.items()}
    files[str(MODULE)] = changes["control_module_sha256"]
    receipt = json.loads((output / "pilot.json").read_bytes())
    expected = dict(changes, archive=key, control_binary_sha256=link["binary"]["sha256"],
                    control_sha256=parent["candidate_sha256"], candidate_sha256=digest(output / Path(key).name),
                    compiler_selected_sources=len(files), parent_sources_sha256=source_list_digest(files),
                    candidate_sources_sha256=source_list_digest({**files, str(MODULE): changes["candidate_module_sha256"]}))
    if (receipt != expected or receipt["parent_sources_sha256"] != parent["candidate_sources_sha256"]
            or receipt["control_sha256"] != digest(ROOT / archive_path(parent))
            or receipt["candidate_sha256"] == receipt["control_sha256"]):
        raise ValueError(f"unexplained compiler input or archive change for {name}")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path, nargs="?")
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--prepare", action="store_true", help="reconstruct pinned Cargo candidates in the build cache")
    parser.add_argument("--cache", action="store_true", help="cache validated batch builds")
    parser.add_argument("--netlink-protocols", action="store_true", help="qualify netlink protocol archives on the scope/realm parent")
    parser.add_argument("--compare", type=Path, help="qualify each netlink candidate against canonical IPRoute2 as it finishes")
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--engine", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.compare and (not args.netlink_protocols or args.prepare or args.cache or args.engine):
        parser.error("--compare requires a netlink protocol batch build")
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    if args.prepare:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            rows = manifest(netlink=args.netlink_protocols)
            list(pool.map(lambda row: prepare(row, netlink=args.netlink_protocols),
                          (v for k, v in rows.items() if Path(k) != BRIDGE)))
        sys.exit(0)
    if not args.link or not args.output:
        parser.error("supply the parent link report and a batch directory")
    raw = args.link.read_bytes()
    link = json.loads(raw)
    if args.netlink_protocols:
        from iproute2_route_name_archives import netlink_control_view, verified_records
        link = netlink_control_view(link)
        verified_records(link, link["iproute2_route_names"])
    else:
        link = build_control_view(link)
    records = selected_records(link)
    if len(records) != 18:
        parser.error("expected all 18 address-protocol parents")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    engines = {Path(key).stem.removeprefix("lib").removesuffix("_audit"): key for key in records}
    if args.cache:
        pinned_rows = manifest(netlink=args.netlink_protocols)
        for name, key in engines.items():
            row = check(link, key, output / name, netlink_protocols=args.netlink_protocols)
            if pinned_rows[key] != row:
                raise ValueError(f"{name}: refusing an unqualified archive")
            prepare(row, output / name / Path(key).name, netlink=args.netlink_protocols)
    elif args.engine:
        check(link, engines[args.engine], output / args.engine, netlink_protocols=args.netlink_protocols)
    else:
        if args.compare:
            from test_iproute2_netlink_protocols import qualify_archive
            args.compare.mkdir(parents=True, exist_ok=True)
            pilot = json.loads((ROOT / "evidence/iproute2-netlink-protocols-pilot.json").read_bytes())

        def one(name):
            with (output / (name + ".log")).open("w") as log:
                subprocess.run([sys.executable, "-B", __file__, args.link.resolve(), output, "--engine", name,
                                *(["--netlink-protocols"] if args.netlink_protocols else [])],
                               stdout=log, stderr=subprocess.STDOUT, check=True)
            print(f"{name} verified", flush=True)
            row = json.loads((output / name / "pilot.json").read_bytes())
            if args.compare:
                qualify_archive(engines[name], row, output, args.link, args.compare, pilot)
            return row

        # Start large crates first so the remaining small builds can overlap them.
        order = sorted(engines, key=lambda n: (-records[engines[n]]["compiler_selected_sources"], n))
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            rows = list(pool.map(one, order))
        if args.link.read_bytes() != raw:
            raise ValueError("release changed during scope/realm builds")
        (output / "archives.json").write_text(json.dumps({r["archive"]: r for r in rows}, indent=2, sort_keys=True) + "\n")
