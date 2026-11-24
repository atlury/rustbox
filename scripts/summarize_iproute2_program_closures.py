#!/usr/bin/env python3
"""Validate and summarize reproducible IPRoute2 per-engine source closures."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from normalize_iproute2 import ENTRYPOINTS


EXPECTED_COUNTS = {
    "arpd": 11,
    "bridge": 20,
    "dcb": 23,
    "devlink": 15,
    "dpll": 13,
    "genl": 13,
    "ifstat": 11,
    "ip": 100,
    "lnstat": 12,
    "netshaper": 13,
    "nstat": 11,
    "rdma": 30,
    "rtacct": 11,
    "rtmon": 11,
    "ss": 20,
    "tc": 112,
    "tipc": 22,
    "vdpa": 12,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--maps-directory", required=True, type=Path)
    parser.add_argument("--engines-directory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if set(ENTRYPOINTS) != set(EXPECTED_COUNTS) or len(ENTRYPOINTS) != 18:
        raise RuntimeError("IPRoute2 normalized engine inventory changed")

    checksum_lines = (args.maps_directory / "maps.sha256").read_text().splitlines()
    expected_map_hashes = {}
    for line in checksum_lines:
        digest, name = line.split(maxsplit=1)
        name = name.removeprefix("*").removeprefix("./")
        if name in expected_map_hashes:
            raise RuntimeError(f"duplicate IPRoute2 linker-map checksum: {name}")
        expected_map_hashes[name] = digest
    expected_map_names = {f"{name}.map" for name in ENTRYPOINTS}
    if set(expected_map_hashes) != expected_map_names:
        raise RuntimeError("IPRoute2 linker-map checksum inventory changed")

    reproducibility = (args.maps_directory / "reproducibility.log").read_text().splitlines()
    if len(reproducibility) != 18 or any(not line.endswith(": OK") for line in reproducibility):
        raise RuntimeError("IPRoute2 linker maps did not pass two-pass reproducibility")

    map_set = hashlib.sha256()
    map_hashes = {}
    per_engine = {}
    union = set()
    database_input_hashes = set()
    for program in sorted(ENTRYPOINTS):
        map_path = args.maps_directory / f"{program}.map"
        map_hash = sha256(map_path)
        if map_hash != expected_map_hashes[map_path.name]:
            raise RuntimeError(f"IPRoute2 linker map changed after capture: {program}")
        map_hashes[program] = map_hash
        map_set.update(map_path.name.encode() + b"\0" + bytes.fromhex(map_hash))

        engine = args.engines_directory / program
        manifest = json.loads((engine / "closure.json").read_text())
        database_path = engine / "compile_commands.json"
        database = json.loads(database_path.read_text())
        main_source = ENTRYPOINTS[program][0]
        if manifest["program"] != program or manifest["main_source"] != main_source:
            raise RuntimeError(f"IPRoute2 closure identity changed: {program}")
        if manifest["linker_map_sha256"] != map_hash:
            raise RuntimeError(f"IPRoute2 closure map digest changed: {program}")
        if manifest["compile_database_sha256"] != sha256(database_path):
            raise RuntimeError(f"IPRoute2 closure database digest changed: {program}")
        if manifest["source_count"] != EXPECTED_COUNTS[program]:
            raise RuntimeError(f"IPRoute2 closure source count changed: {program}")
        if len(database) != manifest["source_count"]:
            raise RuntimeError(f"IPRoute2 closure command count changed: {program}")
        expected_files = {
            f"/rustbox-iproute2/normalized-clang-18/{source}"
            for source in manifest["sources"]
        }
        if {record["file"] for record in database} != expected_files:
            raise RuntimeError(f"IPRoute2 closure source commands changed: {program}")
        if any(record["arguments"].count("-c") != 1 for record in database):
            raise RuntimeError(f"IPRoute2 closure has malformed command: {program}")
        if any(
            record["arguments"].count("-DRUSTBOX_MULTICALL=1") != 1
            for record in database
        ):
            raise RuntimeError(f"IPRoute2 closure lost multicall define: {program}")

        union.update(manifest["sources"])
        database_input_hashes.add(manifest["compile_database_input_sha256"])
        per_engine[program] = {
            "source_count": manifest["source_count"],
            "archive_objects": len(manifest["archive_objects"]),
            "direct_objects": len(manifest["direct_objects"]),
            "compiler_temporary_objects": manifest["compiler_temporary_objects"],
            "generated_actions": manifest["generated_actions"],
            "linker_map_sha256": map_hash,
            "compile_database_sha256": manifest["compile_database_sha256"],
        }

    if len(database_input_hashes) != 1:
        raise RuntimeError("IPRoute2 per-engine databases used different inputs")
    if len(union) != 261 or sum(EXPECTED_COUNTS.values()) != 460:
        raise RuntimeError("IPRoute2 aggregate closure inventory changed")

    summary = {
        "schema": 1,
        "release": "7.3.0",
        "status": "18 reproducible exact linker-map closures validated",
        "engines": 18,
        "source_counts": EXPECTED_COUNTS,
        "sum_of_engine_source_counts": 460,
        "unique_sources": 261,
        "map_set_sha256": map_set.hexdigest(),
        "compile_database_input_sha256": next(iter(database_input_hashes)),
        "per_engine": per_engine,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "engines": 18,
        "map_set_sha256": summary["map_set_sha256"],
        "source_counts": EXPECTED_COUNTS,
        "sum_of_engine_source_counts": 460,
        "unique_sources": 261,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
