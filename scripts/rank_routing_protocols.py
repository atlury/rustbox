#!/usr/bin/env python3
"""Replay the routing protocol substitution over each selected IPRoute2 engine."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
from hashlib import sha256
import json
from pathlib import Path

from audit_linked_pointers import measure
from build_routing_protocol_pilot import transform
from iproute2_route_name_archives import netlink_path
from check_e2fsprogs_dirhash_arrays import source_list_digest


def rank(path):
    data = path.read_bytes()
    link = json.loads(data)
    current = {netlink_path(row) for row in link["iproute2_netlink_protocols"].values()}
    if len(current) != 18 or not all(str(key) in link["source_library_sha256"] for key in current):
        raise ValueError("expected all 18 selected netlink archives")
    engines = {}
    inputs = {archive: {} for archive in current}

    def visit(archive, module, checksum, source):
        if archive not in current:
            return
        if str(module) in inputs[archive]:
            raise ValueError(f"duplicate compiler input {module} in {archive}")
        inputs[archive][str(module)] = checksum.hex()
        if module.name != "rt_names.rs":
            return
        if str(archive) in engines:
            raise ValueError(f"duplicate route names module in {archive}")
        _, row = transform(source)
        if row["control_module_sha256"] != checksum.hex():
            raise ValueError(f"source hash differs for {archive}")
        engines[str(archive)] = dict(row, module=str(module), control_archive_sha256=link["source_library_sha256"][str(archive)])

    measure(link, inspect_module=visit)
    if path.read_bytes() != data or set(engines) != {str(key) for key in current}:
        raise ValueError("incomplete or changed link during routing protocol scan")
    for archive, modules in inputs.items():
        row = engines[str(archive)]
        row.update(compiler_selected_sources=len(modules), parent_sources_sha256=source_list_digest(modules),
                   candidate_sources_sha256=source_list_digest({**modules, row["module"]: row["candidate_module_sha256"]}))
    return dict(engines=engines, candidate_pointer_types=sum(row["raw_pointer_types_removed"] for row in engines.values()),
                binary_sha256=link["binary"]["sha256"], link_report_sha256=sha256(data).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path)
    args = parser.parse_args()
    print(json.dumps(rank(args.link), indent=2, sort_keys=True))
