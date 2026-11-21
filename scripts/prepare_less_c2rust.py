#!/usr/bin/env python3
"""Create Less 710's exact 38-source multicall C2Rust database."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--normalization", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument("--exclude", action="append", default=[])
    args = parser.parse_args()
    records = json.loads(args.database.read_text())
    normalization = json.loads(args.normalization.read_text())
    if normalization.get("entrypoints") != ["rustbox_less_main", "rustbox_lessecho_main"]:
        raise RuntimeError("Less normalization entrypoints changed")
    source_root = Path("/rustbox-less/normalized-source")
    selected: dict[str, dict[str, object]] = {}
    for original in records:
        source = Path(original["file"]).resolve()
        if not source.is_relative_to(source_root):
            raise RuntimeError(f"Less source escapes normalized closure: {source}")
        relative = source.relative_to(source_root).as_posix()
        if relative in selected:
            raise RuntimeError(f"duplicate Less compile action for {relative}")
        record = json.loads(json.dumps(original))
        arguments = list(record["arguments"])
        if arguments.count("-c") != 1:
            raise RuntimeError(f"malformed Less compile action for {relative}")
        arguments.insert(arguments.index("-c"), "-DRUSTBOX_MULTICALL=1")
        record["arguments"] = arguments
        record["file"] = str(source)
        selected[relative] = record
    expected = set(selected)
    if len(records) != 38 or len(expected) != 38 or {"main.c", "lessecho.c"} - expected:
        raise RuntimeError(f"Less C2Rust closure changed: {sorted(expected)}")
    excluded = set(args.exclude)
    if not excluded <= expected:
        raise RuntimeError(f"unknown Less excluded source: {sorted(excluded - expected)}")
    output_records = [selected[name] for name in sorted(expected - excluded)]
    if args.only:
        requested = set(args.only)
        if excluded:
            raise RuntimeError("Less --only and --exclude are mutually exclusive")
        if not requested <= expected:
            raise RuntimeError(f"unknown Less diagnostic source: {sorted(requested - expected)}")
        output_records = [selected[name] for name in sorted(requested)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_records, indent=2) + "\n")
    print(json.dumps({
        "commands": len(output_records),
        "multicall_define": True,
        "excluded_sources": sorted(excluded),
        "selected_diagnostic_sources": args.only,
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
