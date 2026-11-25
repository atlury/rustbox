#!/usr/bin/env python3
"""Cold-build the remaining compiler-selected copies of the IPRoute2 address-protocol change."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys

from build_iproute2_bridge_address_protocols import BRIDGE, build_bridge_trial
from build_iproute2_address_protocol_pilot import build_pilot
from check_cargo_private_inlines import IPROUTE2_CARGO_ENGINES, ROOT, digest
from iproute2_address_protocol_archive import RECEIPTS, build_control_view, pinned_copies, prepare_record
from stage_iproute2_address_protocols import MODULE, compiler_inputs, replace_table
from check_e2fsprogs_dirhash_arrays import source_list_digest


def check_engine(link, engine, directory):
    key, = (n for n in link["source_library_sha256"] if n.endswith(f"/lib{engine}_audit.a") and "/iproute2-" in n)
    original, files = compiler_inputs(link, key)
    _, changes = replace_table(original)
    sources = {str(k): v for k, v in files.items()}
    expected = dict(changes, archive=key, control_binary_sha256=link["binary"]["sha256"],
                    control_sha256=link["source_library_sha256"][key], compiler_selected_sources=len(files),
                    parent_sources_sha256=source_list_digest(sources),
                    candidate_sources_sha256=source_list_digest({**sources, str(MODULE): changes["candidate_module_sha256"]}))
    if not directory.exists():
        if engine == "bridge":
            build_bridge_trial(directory, link)
        else:
            build_pilot(directory, link, engine)
    record = json.loads((directory / "pilot.json").read_bytes())
    candidate_hash = digest(directory / Path(key).name)
    if record != dict(expected, candidate_sha256=candidate_hash) or candidate_hash == expected["control_sha256"]:
        raise ValueError(f"{engine}: candidate archive or compiler inputs differ")
    return dict(record, parent_receipts={k: link[k][key] for k in RECEIPTS if key in link.get(k, {})})


def run(report, output, jobs):
    raw = report.read_bytes()
    original = json.loads(raw)
    link = build_control_view(original)
    output.mkdir(parents=True, exist_ok=True)
    packages = sorted((set(IPROUTE2_CARGO_ENGINES) | {"bridge"}) - {"ip"})

    def one(engine):
        with (output / f"{engine}.log").open("w") as log:
            subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), str(report), str(output), "--engine", engine],
                           cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
        print(f"{engine} verified", flush=True)
        return check_engine(link, engine, output / engine)

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        records = list(pool.map(one, packages))
    if report.read_bytes() != raw:
        raise ValueError("control link changed during batch build")
    (output / "archives.json").write_text(json.dumps({r["archive"]: r for r in records}, sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("control", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--cache", action="store_true", help="publish verified batch archives into the pinned build cache")
    parser.add_argument("--engine", choices=(*IPROUTE2_CARGO_ENGINES, "bridge"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    if args.cache:
        current = build_control_view(json.loads(args.control.read_bytes()))
        for key, record in pinned_copies().items():
            engine = "bridge" if Path(key) == BRIDGE else Path(key).parent.parent.name
            directory = args.output / engine
            if check_engine(current, engine, directory) != record:
                raise ValueError(f"{engine}: batch artifact differs from the production manifest")
            prepare_record(record, directory / Path(key).name)
    elif args.engine:
        check_engine(build_control_view(json.loads(args.control.read_bytes())), args.engine, args.output / args.engine)
    else:
        run(args.control.resolve(), args.output.resolve(), args.jobs)
