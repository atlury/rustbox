#!/usr/bin/env python3
"""Record the compiler inventory and rankings for a verified multicall pointer reduction."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from check_cargo_private_inlines import ROOT, LINK_REPORT, digest
from iproute2_route_name_archives import lookup_records, manifest
from test_inline_release import all_packages


def record(binary, results, rankings):
    evidence = ROOT / "evidence"
    release_file = results / "release.json"
    release = json.loads(release_file.read_bytes())
    binary_sha = digest(binary)
    link_sha = digest(release_file)
    if digest(LINK_REPORT) != link_sha or release["binary"]["sha256"] != binary_sha:
        raise ValueError("snapshot, test release and selected multicall must match")
    rows = manifest(netlink=True)
    if release["iproute2_netlink_protocols"] != rows:
        raise ValueError("the release selected different netlink protocol archives")
    curl = release.get("curl_manual")
    timestamps = release.get("tar_borrowed_timestamps")
    lengths = release.get("bison_literal_lengths")
    dictionary = release.get("lz4_benchmark_dictionary")
    routing = release.get("iproute2_routing_protocols")
    replay_name = "rustbox-netlink-protocol-replays"
    for record, name in ((curl, "rustbox-curl-manual-replays"), (timestamps, "rustbox-tar-timestamps-replays"),
                         (lengths, "rustbox-bison-length-replays"), (routing, "rustbox-routing-protocol-replays"),
                         (dictionary, "rustbox-lz4-dictionary-replays")):
        if record:
            replay_name = name
    inputs = {
        replay_name: results / "replays.json",
        "rustbox-linked-pointers": results / "inventory.json",
        "rustbox-foreign-declaration-candidates": rankings / "foreign.json",
        "rustbox-fixed-array-candidates": rankings / "fixed-arrays.json",
        "rustbox-shared-module-candidates": rankings / "shared-modules.json",
        "rustbox-static-name-tables": rankings / "name-tables.json",
    }
    payloads = {name: source.read_bytes() for name, source in inputs.items()}
    reports = {name: json.loads(data) for name, data in payloads.items()}
    for name, report in reports.items():
        if report["binary_sha256"] != binary_sha or report["link_report_sha256"] != link_sha:
            raise ValueError(f"{name} was measured against a different release")
    replay = reports[replay_name]
    if (replay["previous_link_report_sha256"] != digest(results / "control.json")
            or replay["packages"] != dict.fromkeys(all_packages(), 0)):
        raise ValueError("package results or tested parent differ")
    pilot = json.loads((evidence / "iproute2-netlink-protocols-pilot.json").read_bytes())
    profiles = pilot["profiles"]
    tested = lookup_records(release)
    expected = {
        "archive_sha256": {key: row["candidate_sha256"] for key, row in tested.items()},
        "canonical_lookups": len(rows) * sum(p["forward"] + p["reverse"] for p in profiles),
        "memcheck_runs": len(rows) * pilot["memcheck_runs"],
        "public_commands_per_dispatch_mode": sum(p["public_commands"] for p in profiles),
    }
    if replay["iproute2_netlink_protocols"] != expected:
        raise ValueError("canonical tests do not cover the selected archives and public commands")
    inventory = reports["rustbox-linked-pointers"]
    deltas = inventory["iproute2_netlink_protocol_deltas"]
    if {k: d["raw_pointer_type_tokens"] for k, d in deltas.items()} != {
            k: row["raw_pointer_types_removed_in_pilot_module"] for k, row in rows.items()}:
        raise ValueError("compiled inventory and per-engine reductions differ")
    if dictionary:
        from test_lz4_dictionary_multicall import verify_release
        verify_release(release, json.loads((results / "control.json").read_bytes()), inventory, replay["lz4_benchmark_dictionary"])
    if routing:
        from test_routing_protocol_multicall import expected_binary, validate_coverage
        preview = json.loads((evidence / "iproute2-routing-protocol-multicall.json").read_bytes())
        tested_routes = replay["iproute2_routing_protocols"]
        if (expected_binary(preview, release) != binary_sha or tested_routes["elf_sha256"] != binary_sha
                or {k: d["raw_pointer_type_tokens"] for k, d in inventory["routing_protocol_deltas"].items()}
                != {k: r["raw_pointer_types_removed"] for k, r in routing.items()}):
            raise ValueError("routing reader inventory or tested executable differs from the selected archives")
        validate_coverage(preview, tested_routes)
    if lengths:
        from bison_length_archive import selection
        row = selection.pinned()["pilot"]
        preview = json.loads((evidence / "bison-literal-length-multicall.json").read_bytes())
        prior = json.loads((results / "control.json").read_bytes())
        if (lengths != selection.pinned() or lengths["preview_elf_sha256"] != preview["candidate"]["sha256"]
                or (prior["binary"]["sha256"] == preview["parent"]["sha256"] and binary_sha != lengths["preview_elf_sha256"])
                or inventory["bison_length_deltas"][row["archive"]]["raw_pointer_type_tokens"] != row["raw_pointer_types_removed"]
                or replay["bison_literal_lengths"] != dict(canonical=preview["canonical"], multicall_sha256=binary_sha)):
            raise ValueError("Bison lengths, compiler inputs or parser comparisons differ")
    if timestamps:
        from tar_timespec_archive import selection
        row = selection.pinned()["pilot"]
        preview = json.loads((evidence / "tar-borrowed-timespec-multicall.json").read_bytes())
        expected = {k: preview[k] for k in ("canonical_cases", "memcheck_runs", "restored_file_and_symlink_mtime_ns",
                                             "command_driver_sha256")}
        prior = json.loads((results / "control.json").read_bytes())
        if (timestamps["preview_elf_sha256"] != preview["candidate"]["sha256"]
                or (prior["binary"]["sha256"] == preview["parent"]["sha256"] and binary_sha != timestamps["preview_elf_sha256"])
                or timestamps != selection.pinned() or inventory["tar_timestamp_deltas"][row["archive"]]["raw_pointer_type_tokens"] != 7
                or replay["tar_borrowed_timestamps"] != dict(expected, multicall_sha256=binary_sha)):
            raise ValueError("tar timestamp sources or tested multicall differ from the qualified archive")
    if curl:
        qualified = json.loads((evidence / "curl-manual-pilot.json").read_bytes())
        row = curl["pilot"]
        curl_delta = inventory["curl_manual_deltas"][row["archive"]]["raw_pointer_type_tokens"]
        if replay["curl_manual"] != dict(qualified, multicall_sha256=binary_sha) or curl_delta != row["raw_pointer_types_removed_in_pilot_module"]:
            raise ValueError("curl manual comparison or linked inventory differs from the qualified archive")
    for package in ("rustbox", "inetutils-2.8", "e2fsprogs-1.47.4", "iproute2-7.3.0", "curl-8.23.0"):
        summary = json.loads((evidence / f"{package}-multicall.json").read_bytes())
        if summary["binary"]["sha256"] != binary_sha:
            raise ValueError(f"{package} summary belongs to a different executable")
    for name, data in payloads.items():
        target = evidence / (name + ".json")
        with NamedTemporaryFile(dir=evidence, delete=False) as tmp:
            tmp.write(data)
        staged = Path(tmp.name)
        staged.chmod(0o644)
        staged.replace(target)
    print(f"Recorded {len(rows)} engine archives and {len(replay['packages'])} package suites for {binary_sha}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path, help="tested Linux multicall executable")
    parser.add_argument("results", type=Path, help="completed verify_dirhash_release output directory")
    parser.add_argument("rankings", type=Path, help="directory with foreign.json, fixed-arrays.json, shared-modules.json and name-tables.json")
    args = parser.parse_args()
    record(args.binary, args.results, args.rankings)
