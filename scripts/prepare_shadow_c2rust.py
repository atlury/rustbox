#!/usr/bin/env python3
"""Select the complete normalized public Shadow closure for strict C2Rust."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
from pathlib import Path


SOURCE_ROOT = Path("/work/work/normalized/shadow-4.20.4")
EXCLUDED_NOINST_PROGRAMS = {
    "src/check_subid_range.c",
    "src/free_subid_range.c",
    "src/get_subid_owners.c",
    "src/new_subid_range.c",
    "src/sulogin.c",
}


def arguments(record: dict[str, object]) -> list[str]:
    values = record.get("arguments")
    if values is None:
        values = shlex.split(str(record["command"]))
    return [str(value) for value in values]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--oracle", required=True, type=Path)
    parser.add_argument("--normalization", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    records = json.loads(args.database.read_text())
    oracle = json.loads(args.oracle.read_text())
    normalization = json.loads(args.normalization.read_text())
    all_sources = set(oracle["production_closure"]["relative_paths"])
    expected = all_sources - EXCLUDED_NOINST_PROGRAMS
    if (
        len(all_sources) != 201
        or not EXCLUDED_NOINST_PROGRAMS.issubset(all_sources)
        or len(expected) != 196
        or normalization["scope"]["entrypoint_engines"] != 30
    ):
        raise RuntimeError("Shadow verified source or entrypoint closure changed")

    selected = {}
    excluded = set()
    for original in records:
        source = Path(original["file"]).resolve()
        if not source.is_relative_to(SOURCE_ROOT):
            raise RuntimeError(f"Shadow compile action escapes normalized source: {source}")
        relative = source.relative_to(SOURCE_ROOT).as_posix()
        if relative in EXCLUDED_NOINST_PROGRAMS:
            excluded.add(relative)
            continue
        if relative not in expected:
            raise RuntimeError(f"unexpected Shadow production source: {relative}")
        if relative in selected:
            raise RuntimeError(f"duplicate Shadow compile action: {relative}")
        record = dict(original)
        compile_args = arguments(record)
        if compile_args.count("-c") != 1:
            raise RuntimeError(f"malformed Shadow compile action: {relative}")
        compile_args[compile_args.index("-c"):compile_args.index("-c")] = [
            "-DRUSTBOX_MULTICALL=1"
        ]
        record.pop("command", None)
        record["arguments"] = compile_args
        record["file"] = str(SOURCE_ROOT / relative)
        selected[relative] = record
    if set(selected) != expected or excluded != EXCLUDED_NOINST_PROGRAMS:
        raise RuntimeError(
            f"Shadow C2Rust closure changed: excluded={sorted(excluded)}, "
            f"delta={sorted(set(selected) ^ expected)}"
        )

    output_records = [selected[relative] for relative in sorted(selected)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_records, indent=2) + "\n")
    manifest = {
        "schema": 1,
        "commands": len(output_records),
        "canonical_production_sources": len(all_sources),
        "excluded_noninstalled_program_sources": sorted(EXCLUDED_NOINST_PROGRAMS),
        "included_sources": sorted(selected),
        "multicall_define": True,
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }
    manifest_path = args.output.parent / "closure.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "commands": len(output_records),
        "excluded_noninstalled_programs": len(excluded),
        "multicall_define": True,
        "sha256": manifest["sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
