#!/usr/bin/env python3
"""Create GNU Gzip's exact 68-source portable C2Rust database."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def source_name(path: Path) -> str:
    source_root = Path("/rustbox-gzip/normalized-source")
    build_root = Path("/rustbox-gzip/normalized-clang")
    if path.is_relative_to(source_root):
        return path.relative_to(source_root).as_posix()
    if path == build_root / "version.c":
        return "<generated>/version.c"
    raise RuntimeError(f"GNU Gzip source escapes normalized production closure: {path}")


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
    expected = set(normalization["scope"]["sources"]["clang"])
    selected: dict[str, dict[str, object]] = {}

    for original in records:
        source = Path(original["file"]).resolve()
        relative = source_name(source)
        if relative in selected:
            raise RuntimeError(f"duplicate GNU Gzip compile action for {relative}")
        record = json.loads(json.dumps(original))
        arguments = list(record["arguments"])
        if arguments.count("-c") != 1:
            raise RuntimeError(f"malformed GNU Gzip compile action for {relative}")
        arguments.insert(arguments.index("-c"), "-DRUSTBOX_MULTICALL=1")
        record["arguments"] = arguments
        record["file"] = str(source)
        selected[relative] = record

    if len(records) != 68 or len(selected) != 68 or set(selected) != expected:
        raise RuntimeError(
            f"GNU Gzip C2Rust closure changed: {sorted(set(selected) ^ expected)}"
        )
    excluded = set(args.exclude)
    if not excluded <= expected:
        raise RuntimeError(f"unknown GNU Gzip excluded source: {sorted(excluded - expected)}")
    output_records = [selected[name] for name in sorted(expected - excluded)]
    if args.only:
        requested = set(args.only)
        if not requested <= expected:
            raise RuntimeError(f"unknown GNU Gzip diagnostic source: {sorted(requested - expected)}")
        if excluded:
            raise RuntimeError("GNU Gzip --only and --exclude are mutually exclusive")
        output_records = [selected[name] for name in sorted(requested)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_records, indent=2) + "\n")
    print(json.dumps({
        "commands": len(output_records),
        "multicall_define": True,
        "portable_crc": True,
        "excluded_sources": sorted(excluded),
        "selected_diagnostic_sources": args.only,
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
