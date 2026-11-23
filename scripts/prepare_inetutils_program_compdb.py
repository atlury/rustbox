#!/usr/bin/env python3
"""Select one Inetutils program's exact linker-map source closure."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


SOURCE_ROOT = Path("/rustbox-inetutils/normalized-source")
BUILD_ROOT = Path("/rustbox-inetutils/normalized-clang")
ARCHIVE_MEMBER = re.compile(r"^(?P<archive>\S+\.a)\((?P<member>[^)]+)\)$")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--main-source", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()

    records = json.loads(args.database.read_text())
    by_source: dict[str, dict[str, object]] = {}
    by_object: dict[str, dict[str, object]] = {}
    for record in records:
        source = Path(str(record["file"])).resolve()
        output = Path(str(record["output"])).resolve()
        if not source.is_relative_to(SOURCE_ROOT) or not output.is_relative_to(BUILD_ROOT):
            raise RuntimeError("Inetutils compile action escaped the normalized roots")
        relative_source = source.relative_to(SOURCE_ROOT).as_posix()
        relative_object = output.relative_to(BUILD_ROOT).as_posix()
        if relative_source in by_source or relative_object in by_object:
            raise RuntimeError("duplicate Inetutils compile action")
        by_source[relative_source] = record
        by_object[relative_object] = record

    main_source = args.main_source
    if main_source not in by_source:
        raise RuntimeError(f"missing Inetutils main source: {main_source}")
    selected = {main_source: by_source[main_source]}
    archive_objects: list[str] = []
    for line in args.map.read_text(errors="replace").splitlines():
        if line == "Merging program properties":
            break
        token = line.strip().split(maxsplit=1)[0] if line.strip() else ""
        match = ARCHIVE_MEMBER.match(token)
        if match is None:
            continue
        archive_dir = Path(match.group("archive")).parent.name
        relative_object = f"{archive_dir}/{match.group('member')}"
        record = by_object.get(relative_object)
        if record is None:
            raise RuntimeError(f"no compile action for map object: {relative_object}")
        relative_source = Path(str(record["file"])).relative_to(SOURCE_ROOT).as_posix()
        selected[relative_source] = record
        archive_objects.append(relative_object)

    output_records = []
    for source in sorted(selected):
        record = json.loads(json.dumps(selected[source]))
        arguments = [str(value) for value in record["arguments"]]
        if arguments.count("-c") != 1:
            raise RuntimeError(f"malformed Inetutils compile action: {source}")
        arguments.insert(arguments.index("-c"), "-DRUSTBOX_MULTICALL=1")
        record["arguments"] = arguments
        output_records.append(record)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_records, indent=2) + "\n")
    manifest = {
        "schema": 1,
        "main_source": main_source,
        "sources": sorted(selected),
        "archive_objects": sorted(set(archive_objects)),
        "compile_commands": len(output_records),
        "compile_database_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "linker_map_sha256": hashlib.sha256(args.map.read_bytes()).hexdigest(),
    }
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "main_source": main_source,
        "sources": len(selected),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
