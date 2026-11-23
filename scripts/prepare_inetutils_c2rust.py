#!/usr/bin/env python3
"""Create Inetutils' exact 288-source multicall C2Rust database."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SOURCE_ROOT = Path("/rustbox-inetutils/normalized-source")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--normalization", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--only", action="append", default=[])
    args = parser.parse_args()
    records = json.loads(args.database.read_text())
    normalization = json.loads(args.normalization.read_text())
    expected = set(normalization["build"]["production_sources"])
    if (
        len(normalization["normalization"]["entrypoints"]) != 26
        or len(normalization["normalization"]["changed_sources"]) != 27
        or len(records) != 288
        or len(expected) != 288
    ):
        raise RuntimeError("Inetutils normalized closure changed")

    selected = {}
    for original in records:
        source = Path(str(original["file"])).resolve()
        if not source.is_relative_to(SOURCE_ROOT):
            raise RuntimeError(f"Inetutils source escapes normalized root: {source}")
        relative = source.relative_to(SOURCE_ROOT).as_posix()
        if relative not in expected or relative in selected:
            raise RuntimeError(f"unexpected/duplicate Inetutils source: {relative}")
        selected[relative] = original
    if set(selected) != expected:
        raise RuntimeError("Inetutils compile database does not cover normalized evidence")

    requested = set(args.only)
    if requested and not requested <= expected:
        raise RuntimeError(f"unknown Inetutils diagnostic source: {sorted(requested - expected)}")
    output_records = []
    for relative in sorted(requested or expected):
        record = json.loads(json.dumps(selected[relative]))
        arguments = [str(value) for value in record["arguments"]]
        if arguments.count("-c") != 1:
            raise RuntimeError(f"malformed Inetutils compile action: {relative}")
        arguments.insert(arguments.index("-c"), "-DRUSTBOX_MULTICALL=1")
        record["arguments"] = arguments
        output_records.append(record)
    if len(output_records) != len(requested or expected):
        raise RuntimeError("Inetutils output action count changed")

    closure = hashlib.sha256(("\n".join(sorted(expected)) + "\n").encode()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_records, indent=2) + "\n")
    print(json.dumps({
        "commands": len(output_records),
        "multicall_define": True,
        "production_closure_sha256": closure,
        "selected_diagnostic_sources": args.only,
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
