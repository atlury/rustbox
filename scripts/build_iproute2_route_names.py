#!/usr/bin/env python3
"""Reproduce and qualify all linked IPRoute2 parent archives for the scope/realm substitution."""
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


def check(link, key, output):
    parents = selected_records(link)
    parent = parents[key]
    name = Path(key).stem.removeprefix("lib").removesuffix("_audit")
    if not output.exists():
        if Path(key) == BRIDGE:
            build_bridge_trial(output, link, route_names=True)
        else:
            build_pilot(output, link, name, route_names=True)
    control, files = compiler_inputs(control_view(link), key)
    module, _ = replace_table(control)
    _, changes = replace_route_names(module)
    files = {str(k): v for k, v in files.items()}
    files[str(MODULE)] = changes["control_module_sha256"]
    receipt = json.loads((output / "pilot.json").read_bytes())
    expected = dict(changes, archive=key, control_binary_sha256=link["binary"]["sha256"],
                    control_sha256=parent["candidate_sha256"], candidate_sha256=digest(output / Path(key).name),
                    compiler_selected_sources=len(files), parent_sources_sha256=source_list_digest(files),
                    candidate_sources_sha256=source_list_digest({**files, str(MODULE): changes["candidate_module_sha256"]}))
    if (receipt != expected or receipt["parent_sources_sha256"] != parent["candidate_sources_sha256"]
            or receipt["control_sha256"] != digest(ROOT / candidate_path(parent))
            or receipt["candidate_sha256"] == receipt["control_sha256"]):
        raise ValueError(f"unexplained compiler input or archive change for {name}")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path, nargs="?")
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--prepare", action="store_true", help="reconstruct pinned Cargo candidates in the build cache")
    parser.add_argument("--cache", action="store_true", help="cache validated batch builds")
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--engine", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    if args.prepare:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            list(pool.map(prepare, (v for k, v in manifest().items() if Path(k) != BRIDGE)))
        sys.exit(0)
    if not args.link or not args.output:
        parser.error("supply the parent link report and a batch directory")
    raw = args.link.read_bytes()
    link = build_control_view(json.loads(raw))
    records = selected_records(link)
    if len(records) != 18:
        parser.error("expected all 18 address-protocol parents")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    engines = {Path(key).stem.removeprefix("lib").removesuffix("_audit"): key for key in records}
    if args.cache:
        pinned_rows = manifest()
        for name, key in engines.items():
            row = check(link, key, output / name)
            if pinned_rows[key] != row:
                raise ValueError(f"{name}: refusing an unqualified archive")
            prepare(row, output / name / Path(key).name)
    elif args.engine:
        check(link, engines[args.engine], output / args.engine)
    else:
        def one(name):
            with (output / (name + ".log")).open("w") as log:
                subprocess.run([sys.executable, "-B", __file__, args.link.resolve(), output, "--engine", name],
                               stdout=log, stderr=subprocess.STDOUT, check=True)
            print(f"{name} verified", flush=True)
            return json.loads((output / name / "pilot.json").read_bytes())

        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            rows = list(pool.map(one, sorted(engines)))
        if args.link.read_bytes() != raw:
            raise ValueError("release changed during scope/realm builds")
        (output / "archives.json").write_text(json.dumps({r["archive"]: r for r in rows}, indent=2, sort_keys=True) + "\n")
