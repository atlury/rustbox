#!/usr/bin/env python3
"""Relink owned routing tables and compare both public ip invocation modes on private configurations."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import json
import os
from pathlib import Path

from check_cargo_private_inlines import digest
from link_rustbox_multicall import IPROUTE2_PROGRAMS
from preview_cargo_multicall import preview_link
from preview_routing_protocols import commands, qualified_engines
from stage_dsfield_archives import parent_view
from test_iproute2_route_tables import PROFILES, QUERIES, capture, configure


def exercise(elf, stage, oracle):
    checked = commands(elf, stage)
    local, vendor = Path("/etc/iproute2"), Path("/usr/share/iproute2")
    if not all(os.path.ismount(p) and not any(p.iterdir()) for p in (local, vendor)):
        raise ValueError("expected two empty private configuration mounts")
    if {cc: info["canonical_sha256"]["ip"] for cc, info in checked["canonical"].items()} != oracle["public_oracle_sha256"]:
        raise ValueError("canonical ip binaries differ from archive tests")
    if [p["profile"] for p in oracle["profiles"]] != list(PROFILES):
        raise ValueError("route-table configuration profiles differ")
    for profile in oracle["profiles"]:
        configure(profile["profile"], local, vendor)
        statuses = []
        for query in QUERIES:
            args = ["ip", "-4", "route", "show", "table", query]
            expected = capture(args, executable="/rustbox-iproute2/programs-gcc/ip")
            if (capture(args, executable="/rustbox-iproute2/programs-clang-18/ip") != expected
                    or capture(args, executable=stage / "applets/ip") != expected or capture([elf, *args]) != expected):
                raise ValueError((profile["profile"], query, "multicall routing table filter differs"))
            statuses.append(expected[0])
        if statuses != profile["public_statuses"]:
            raise ValueError("public route-table filters differ from the verified ip archive")
    return dict(checked, route_table_filters=len(PROFILES) * len(QUERIES), profiles=list(PROFILES))


def preview(link, log, batch, output, receipt):
    raw = link.read_bytes()
    release = json.loads(raw)
    parent_view(release)
    proof = json.loads(receipt.read_bytes())
    if proof["link_sha256"] != digest(link) or proof["binary_sha256"] != release["binary"]["sha256"]:
        raise ValueError("archive comparisons belong to a different link")
    rows = proof["verified"]
    ip, = [r for key, r in rows.items() if Path(key).name == "libip_audit.a"]
    names = ["ip"] if len(rows) == 1 else IPROUTE2_PROGRAMS

    def resolve(engine, key, expected):
        directory = batch / Path(key).stem
        pilot = json.loads((directory / "pilot.json").read_bytes())
        tested = rows[key]
        if (pilot["archive"] != key or pilot["control_sha256"] != expected
                or pilot["control_binary_sha256"] != release["binary"]["sha256"]
                or any(tested[k] != v for k, v in pilot.items())
                or tested != json.loads((batch / (Path(key).name + ".json")).read_bytes())):
            raise ValueError(f"route-table qualification differs for {engine}")
        return directory / Path(key).name, pilot["candidate_sha256"]

    prepare = qualified_engines(release, rows, names, resolve)
    def compare(elf, stage):
        return dict(exercise(elf, stage, ip), archive_evidence_sha256=digest(receipt))
    preview_link(link, raw, log, output, prepare, compare)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("link", "log", "batch", "output", "receipt"):
        p.add_argument(name, type=Path)
    args = p.parse_args()
    preview(args.link, args.log, args.batch, args.output, args.receipt)
