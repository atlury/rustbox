#!/usr/bin/env python3
"""Create acl's exact 72-source C2Rust compilation database."""

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
    source_root = Path("/rustbox-acl/normalized-source")
    expected = set(oracle["scope"]["production_sources"])
    grouped: dict[Path, list[dict[str, object]]] = {}
    for original in records:
        source = Path(original["file"]).resolve()
        if not source.is_relative_to(source_root):
            raise RuntimeError(f"acl source escapes normalized production closure: {source}")
        grouped.setdefault(source, []).append(original)

    selected: dict[Path, dict[str, object]] = {}
    relative_names: set[str] = set()
    for source, candidates in grouped.items():
        ordinary = [record for record in candidates if "-fPIC" not in record["arguments"]]
        if len(ordinary) != 1:
            raise RuntimeError(f"acl non-PIC production action changed for {source}: {len(ordinary)}")
        record = json.loads(json.dumps(ordinary[0]))
        arguments = list(record["arguments"])
        if arguments.count("-c") != 1:
            raise RuntimeError(f"malformed acl compile command: {source}")
        arguments.insert(arguments.index("-c"), "-DRUSTBOX_MULTICALL=1")
        record["arguments"] = arguments
        record["file"] = str(source)
        selected[source] = record
        relative_names.add(source.relative_to(source_root).as_posix())

    if len(records) != 137 or len(selected) != 72 or relative_names != expected:
        raise RuntimeError(f"acl C2Rust closure changed: {sorted(relative_names ^ expected)}")
    output_records = [selected[source] for source in sorted(selected)]
    if args.only:
        requested = set(args.only)
        if not requested <= expected:
            raise RuntimeError(f"unknown acl diagnostic source selection: {sorted(requested - expected)}")
        output_records = [
            record for source, record in sorted(selected.items())
            if source.relative_to(source_root).as_posix() in requested
        ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_records, indent=2) + "\n")
    print(json.dumps({
        "commands": len(output_records),
        "multicall_define": True,
        "selected_diagnostic_sources": args.only,
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
