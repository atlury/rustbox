#!/usr/bin/env python3
"""Create LZ4's exact 12-source multithreaded C2Rust database."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--only", action="append", default=[])
    args = parser.parse_args()
    records = json.loads(args.database.read_text())
    oracle = json.loads(args.oracle.read_text())
    source_root = Path("/rustbox-lz4/normalized-clang")
    expected = set(oracle["inventory"]["production_sources"])

    selected: dict[Path, dict[str, object]] = {}
    for original in records:
        source = Path(original["file"]).resolve()
        if not source.is_relative_to(source_root):
            raise RuntimeError(f"LZ4 source escapes normalized production closure: {source}")
        relative = source.relative_to(source_root).as_posix()
        arguments = list(original["arguments"])
        multithreaded = (
            "-DLZ4IO_MULTITHREAD" in arguments and "-DLZ4F_MULTITHREAD=1" in arguments
        )
        if not multithreaded:
            continue
        if source in selected:
            raise RuntimeError(f"duplicate LZ4 multithreaded action for {source}")
        record = json.loads(json.dumps(original))
        if arguments.count("-c") != 1 or "-DLZ4_FORCE_MEMORY_ACCESS=0" not in arguments:
            raise RuntimeError(f"malformed LZ4 compile action for {source}")
        arguments.insert(arguments.index("-c"), "-DRUSTBOX_MULTICALL=1")
        record["arguments"] = arguments
        record["file"] = str(source)
        selected[source] = record

    relative_names = {source.relative_to(source_root).as_posix() for source in selected}
    if len(records) != 24 or len(selected) != 12 or relative_names != expected:
        raise RuntimeError(f"LZ4 C2Rust closure changed: {sorted(relative_names ^ expected)}")
    output_records = [selected[source] for source in sorted(selected)]
    if args.only:
        requested = set(args.only)
        if not requested <= expected:
            raise RuntimeError(f"unknown LZ4 diagnostic source: {sorted(requested - expected)}")
        output_records = [
            record for source, record in sorted(selected.items())
            if source.relative_to(source_root).as_posix() in requested
        ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_records, indent=2) + "\n")
    print(json.dumps({
        "commands": len(output_records),
        "multicall_define": True,
        "multithreaded": True,
        "portable_memory_access": True,
        "selected_diagnostic_sources": args.only,
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
