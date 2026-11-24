#!/usr/bin/env python3
"""Validate and summarize reproducible E2fsprogs per-engine closures."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from normalize_e2fsprogs import ENTRYPOINTS


EXPECTED_COUNTS = {
    "badblocks": 59,
    "chattr": 10,
    "debugfs": 124,
    "dumpe2fs": 71,
    "e2freefrag": 58,
    "e2fsck": 114,
    "e2image": 65,
    "e2initrd_helper": 61,
    "e2undo": 60,
    "e4crypt": 2,
    "e4defrag": 57,
    "filefrag": 1,
    "fsck": 4,
    "fuse2fs": 65,
    "logsave": 1,
    "lsattr": 9,
    "mke2fs": 96,
    "mklost_found": 1,
    "resize2fs": 76,
    "tune2fs": 87,
}
EXPECTED_GENERATED_SOURCES = {
    "@build/debugfs/debug_cmds.c",
    "@build/debugfs/extent_cmds.c",
    "@build/lib/ext2fs/ext2_err.c",
    "@build/lib/ss/ss_err.c",
    "@build/lib/ss/std_rqs.c",
    "@build/lib/support/prof_err.c",
    "@build/misc/default_profile.c",
}
SOURCE_ROOT = Path("/work/work/normalized/e2fsprogs-1.47.4")
BUILD_ROOT = Path("/rustbox-e2fsprogs/normalized-clang-18")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_file(source: str) -> str:
    if source.startswith("@build/"):
        return str(BUILD_ROOT / source.removeprefix("@build/"))
    return str(SOURCE_ROOT / source)


def action_sha256(record: dict[str, object]) -> str:
    encoded = json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--normalization-manifest", required=True, type=Path)
    parser.add_argument("--maps-directory", required=True, type=Path)
    parser.add_argument("--engines-directory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    inventory = dict(ENTRYPOINTS)
    if set(inventory) != set(EXPECTED_COUNTS) or len(inventory) != 20:
        raise RuntimeError("E2fsprogs normalized engine inventory changed")
    normalization = json.loads(args.normalization_manifest.read_text())
    if (
        normalization.get("release") != "1.47.4"
        or normalization.get("native_engines") != 20
        or normalization.get("native_names") != 28
    ):
        raise RuntimeError("E2fsprogs normalization coverage changed")

    checksum_lines = (args.maps_directory / "maps.sha256").read_text().splitlines()
    expected_map_hashes = {}
    for line in checksum_lines:
        digest, name = line.split(maxsplit=1)
        name = name.removeprefix("*").removeprefix("./")
        if name in expected_map_hashes:
            raise RuntimeError(f"duplicate E2fsprogs map checksum: {name}")
        expected_map_hashes[name] = digest
    expected_map_names = {f"{name}.map" for name in inventory}
    if set(expected_map_hashes) != expected_map_names:
        raise RuntimeError("E2fsprogs linker-map checksum inventory changed")

    reproducibility = (
        args.maps_directory / "reproducibility.log"
    ).read_text().splitlines()
    if len(reproducibility) != 20 or any(
        not line.endswith(": OK") for line in reproducibility
    ):
        raise RuntimeError("E2fsprogs linker maps failed two-pass reproducibility")

    map_set = hashlib.sha256()
    database_input_hashes = set()
    source_union = set()
    object_union = set()
    generated_union = set()
    per_engine = {}
    for program in sorted(inventory):
        map_path = args.maps_directory / f"{program}.map"
        map_hash = sha256(map_path)
        if map_hash != expected_map_hashes[map_path.name]:
            raise RuntimeError(f"E2fsprogs linker map changed after capture: {program}")
        map_set.update(map_path.name.encode() + b"\0" + bytes.fromhex(map_hash))

        engine = args.engines_directory / program
        manifest = json.loads((engine / "closure.json").read_text())
        database_path = engine / "compile_commands.json"
        database = json.loads(database_path.read_text())
        if manifest["program"] != program or manifest["main_source"] != inventory[program]:
            raise RuntimeError(f"E2fsprogs closure identity changed: {program}")
        if manifest["linker_map_sha256"] != map_hash:
            raise RuntimeError(f"E2fsprogs closure map digest changed: {program}")
        if manifest["compile_database_sha256"] != sha256(database_path):
            raise RuntimeError(f"E2fsprogs closure database digest changed: {program}")
        if (
            manifest["source_count"] != EXPECTED_COUNTS[program]
            or manifest["object_count"] != EXPECTED_COUNTS[program]
            or len(database) != EXPECTED_COUNTS[program]
        ):
            raise RuntimeError(f"E2fsprogs closure count changed: {program}")
        if {record["file"] for record in database} != {
            expected_file(source) for source in manifest["sources"]
        }:
            raise RuntimeError(f"E2fsprogs closure source actions changed: {program}")
        if set(manifest["source_sha256"]) != set(manifest["sources"]) or any(
            manifest["source_sha256"][source]
            != sha256(Path(expected_file(source)))
            for source in manifest["sources"]
        ):
            raise RuntimeError(f"E2fsprogs closure source hashes changed: {program}")
        if {
            Path(record["output"]).relative_to(BUILD_ROOT).as_posix()
            for record in database
        } != set(manifest["objects"]):
            raise RuntimeError(f"E2fsprogs closure object actions changed: {program}")
        action_hashes = {
            Path(record["output"]).relative_to(BUILD_ROOT).as_posix():
            action_sha256(record)
            for record in database
        }
        if action_hashes != manifest["compile_action_sha256"]:
            raise RuntimeError(f"E2fsprogs closure action hashes changed: {program}")
        if any(record["arguments"].count("-c") != 1 for record in database):
            raise RuntimeError(f"E2fsprogs closure has malformed action: {program}")
        if any(
            record["arguments"].count("-DRUSTBOX_MULTICALL=1") != 1
            for record in database
        ):
            raise RuntimeError(f"E2fsprogs closure lost multicall define: {program}")

        source_union.update(manifest["sources"])
        object_union.update(manifest["objects"])
        generated_union.update(manifest["generated_sources"])
        database_input_hashes.add(manifest["compile_database_input_sha256"])
        per_engine[program] = {
            "source_count": manifest["source_count"],
            "archive_objects": len(manifest["archive_objects"]),
            "direct_objects": len(manifest["direct_objects"]),
            "generated_sources": manifest["generated_sources"],
            "linker_map_sha256": map_hash,
            "compile_database_sha256": manifest["compile_database_sha256"],
        }

    if len(database_input_hashes) != 1:
        raise RuntimeError("E2fsprogs closures used different compile databases")
    if (
        sum(EXPECTED_COUNTS.values()) != 1021
        or len(source_union) != 209
        or len(object_union) != 217
        or generated_union != EXPECTED_GENERATED_SOURCES
    ):
        raise RuntimeError("E2fsprogs aggregate closure inventory changed")

    summary = {
        "schema": 1,
        "release": "1.47.4",
        "status": "20 reproducible exact linker-map closures validated",
        "engines": 20,
        "native_names": normalization["native_names"],
        "source_counts": EXPECTED_COUNTS,
        "sum_of_engine_source_counts": 1021,
        "unique_sources": 209,
        "unique_objects": 217,
        "generated_sources": sorted(generated_union),
        "map_set_sha256": map_set.hexdigest(),
        "compile_database_input_sha256": next(iter(database_input_hashes)),
        "per_engine": per_engine,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "engines": 20,
        "map_set_sha256": summary["map_set_sha256"],
        "sum_of_engine_source_counts": 1021,
        "unique_sources": 209,
        "unique_objects": 217,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
