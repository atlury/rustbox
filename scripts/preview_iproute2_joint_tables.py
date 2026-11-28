#!/usr/bin/env python3
"""Exercise route-table, device-group and DS-field lookups in one complete Rustbox executable."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
from hashlib import sha256
import json
from pathlib import Path

from check_cargo_private_inlines import digest
from link_rustbox_multicall import IPROUTE2_PROGRAMS
from preview_cargo_multicall import preview_link
from preview_iproute2_combined_names import combined_commands
from preview_iproute2_route_tables import exercise
from preview_routing_protocols import qualified_engines
from stage_dsfield_archives import parent_view
from test_iproute2_route_tables import configure


def preview(link, log, batch, output, receipt):
    raw = link.read_bytes()
    release = json.loads(raw)
    parent_view(release)
    proof = json.loads(receipt.read_bytes())
    rows = proof["engines"]
    if (proof["link_sha256"] != sha256(raw).hexdigest() or proof["parent_binary_sha256"] != release["binary"]["sha256"]
            or set(rows) not in ({"ip"}, set(IPROUTE2_PROGRAMS))):
        raise ValueError("expected the qualified ip engine or the complete joint batch on this link")
    selected = {item["archive"]["archive"]: item for item in rows.values()}

    def resolve(name, key, expected):
        pilot = rows[name]["archive"]
        archive = batch / name / Path(key).name
        if (pilot != json.loads((archive.parent / "pilot.json").read_bytes()) or pilot["archive"] != key
                or pilot["control_sha256"] != expected or pilot["control_binary_sha256"] != release["binary"]["sha256"]):
            raise ValueError(f"unexpected compiler archive for {name}")
        for kind, item in rows[name]["comparisons"].items():
            if digest(batch / f"{name}-{kind}.json") != item["report_sha256"]:
                raise ValueError(f"{name} archive test differs for {kind}")
        if set(rows[name]["comparisons"]) != {"group", "route"}:
            raise ValueError(f"{name} requires both oracle suites")
        return archive, pilot["candidate_sha256"]

    def compare(elf, stage):
        route = exercise(elf, stage, rows["ip"]["comparisons"]["route"])
        configure("empty", Path("/etc/iproute2"), Path("/usr/share/iproute2"))
        groups = combined_commands(elf, stage, checked=route)
        if groups["canonical"] != route["canonical"]:
            raise ValueError("canonical ip binaries changed between suites")
        return dict(groups, route_table_filters=route["route_table_filters"], route_table_profiles=route["profiles"],
                    archive_evidence_sha256=digest(receipt))

    preview_link(link, raw, log, output, qualified_engines(release, selected, rows, resolve), compare)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("link", "log", "batch", "output", "receipt"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    preview(args.link, args.log, args.batch, args.output, args.receipt)
