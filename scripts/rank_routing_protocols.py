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


def rank(path, *, dsfield=False, group_names=False):
    data = path.read_bytes()
    link = json.loads(data)
    if group_names:
        from build_group_names import transform as replace_table
        from iproute2_route_name_archives import lookup_archive, lookup_records
        if dsfield or "iproute2_routing_protocols" not in link:
            raise ValueError("device group names require a routing release and one requested table")
        current = {lookup_archive(link, key) for key in lookup_records(link)}
    elif dsfield:
        from build_dsfield_names import transform as replace_table
        from stage_routing_protocol_archives import FIELD, candidate_path, parent_view
        parent_view(link)  # Validate every preceding routing archive and native C-string selection.
        current = {candidate_path(row) for row in link[FIELD].values()}
    else:
        replace_table = transform
        current = {netlink_path(row) for row in link["iproute2_netlink_protocols"].values()}
    if len(current) != 18 or not all(str(key) in link["source_library_sha256"] for key in current):
        raise ValueError("expected all 18 selected IPRoute2 archives")
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
        candidate, row = replace_table(source)
        if group_names and "iproute2_dsfield_names" not in link:
            from build_dsfield_names import transform as replace_dsfield
            first, _ = replace_dsfield(candidate)
            second, _ = replace_table(replace_dsfield(source)[0])
            if first != second:
                raise ValueError(f"DS field and group-name edits differ by selection order in {archive}")
            row["with_dsfield_module_sha256"] = sha256(first).hexdigest()
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
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--group-names", action="store_true", help="inspect device group lookups in the selected engines")
    selection.add_argument("--dsfield", action="store_true", help="inspect DS field names after routing protocol replacement")
    args = parser.parse_args()
    print(json.dumps(rank(args.link, dsfield=args.dsfield, group_names=args.group_names), indent=2, sort_keys=True))
