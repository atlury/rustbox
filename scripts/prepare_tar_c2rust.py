#!/usr/bin/env python3
"""Create GNU tar's exact 197-source multicall C2Rust database."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


SOURCE_ROOT = Path("/rustbox-tar/normalized-clang")


def replace_root(value: str, destination: Path) -> str:
    prefix = str(SOURCE_ROOT)
    if value == prefix:
        return str(destination)
    if value.startswith(prefix + "/"):
        return str(destination) + value[len(prefix):]
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--oracle", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-output", required=True, type=Path)
    parser.add_argument("--only", action="append", default=[])
    args = parser.parse_args()
    records = json.loads(args.database.read_text())
    oracle = json.loads(args.oracle.read_text())
    expected = set(oracle["inventory"]["production_sources"])
    if len(records) != 197 or len(expected) != 197:
        raise RuntimeError("GNU tar production database or oracle closure changed")

    selected: dict[str, dict[str, object]] = {}
    for original in records:
        source = Path(str(original["file"])).resolve()
        if not source.is_relative_to(SOURCE_ROOT):
            raise RuntimeError(f"GNU tar source escapes normalized closure: {source}")
        relative = source.relative_to(SOURCE_ROOT).as_posix()
        if relative not in expected:
            raise RuntimeError(f"unexpected GNU tar production source: {relative}")
        if relative in selected:
            raise RuntimeError(f"duplicate GNU tar compile action: {relative}")
        selected[relative] = original
    if set(selected) != expected:
        raise RuntimeError(f"GNU tar C2Rust closure changed: {sorted(set(selected) ^ expected)}")

    if args.source_output.exists():
        shutil.rmtree(args.source_output)
    shutil.copytree(
        SOURCE_ROOT,
        args.source_output,
        symlinks=True,
        ignore=shutil.ignore_patterns(
            ".deps", ".libs", "*.o", "*.a",
            "testsuite.dir", "testsuite.log", "test-suite.log",
        ),
    )

    requested = set(args.only)
    if requested and not requested <= expected:
        raise RuntimeError(f"unknown GNU tar diagnostic source: {sorted(requested - expected)}")
    names = sorted(requested or expected)
    output_records: list[dict[str, object]] = []
    for relative in names:
        record = json.loads(json.dumps(selected[relative]))
        arguments = list(record["arguments"])
        if arguments.count("-c") != 1:
            raise RuntimeError(f"malformed GNU tar compile action: {relative}")
        arguments.insert(arguments.index("-c"), "-DRUSTBOX_MULTICALL=1")
        record["arguments"] = [replace_root(str(value), args.source_output) for value in arguments]
        record["directory"] = replace_root(str(record["directory"]), args.source_output)
        record["file"] = replace_root(str(record["file"]), args.source_output)
        record["output"] = replace_root(str(record["output"]), args.source_output)
        output_records.append(record)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_records, indent=2) + "\n")
    print(json.dumps({
        "commands": len(output_records),
        "multicall_define": True,
        "production_sources": len(expected),
        "selected_diagnostic_sources": args.only,
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
