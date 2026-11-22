#!/usr/bin/env python3
"""Create Ncurses' exact 264-source multicall C2Rust database."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


SOURCE_ROOT = Path("/rustbox-ncurses/normalized-clang")
EXPECTED_CLOSURE = "1bc8f0759a62f64488c020bf908e391bd35cc5b637959b3b837d022696609eaf"


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
    parser.add_argument("--normalization", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-output", required=True, type=Path)
    parser.add_argument("--only", action="append", default=[])
    args = parser.parse_args()
    records = json.loads(args.database.read_text())
    normalization = json.loads(args.normalization.read_text())
    if (len(normalization.get("changed_sources", [])), normalization.get("entrypoints")) != (9, 7):
        raise RuntimeError("Ncurses normalization manifest changed")
    if len(records) != 515:
        raise RuntimeError("Ncurses Clang compile-action count changed")

    selected: dict[str, dict[str, object]] = {}
    for original in records:
        source = Path(str(original["file"])).resolve()
        if not source.is_relative_to(SOURCE_ROOT):
            raise RuntimeError(f"Ncurses source escapes normalized closure: {source}")
        relative = source.relative_to(SOURCE_ROOT).as_posix()
        selected.setdefault(relative, original)
    names = sorted(selected)
    closure = hashlib.sha256(("\n".join(names) + "\n").encode()).hexdigest()
    if len(names) != 264 or closure != EXPECTED_CLOSURE:
        raise RuntimeError("Ncurses C2Rust source closure changed")

    if args.source_output.exists():
        shutil.rmtree(args.source_output)
    shutil.copytree(
        SOURCE_ROOT,
        args.source_output,
        symlinks=True,
        ignore=shutil.ignore_patterns(".deps", ".libs", "*.o", "*.a", "*.so", "*.so.*"),
    )

    requested = set(args.only)
    if requested and not requested <= set(names):
        raise RuntimeError(f"unknown Ncurses diagnostic source: {sorted(requested - set(names))}")
    output_records: list[dict[str, object]] = []
    for relative in sorted(requested or set(names)):
        record = json.loads(json.dumps(selected[relative]))
        arguments = list(record["arguments"])
        if arguments.count("-c") != 1:
            raise RuntimeError(f"malformed Ncurses compile action: {relative}")
        arguments.insert(arguments.index("-c"), "-DRUSTBOX_MULTICALL=1")
        record["arguments"] = [replace_root(str(value), args.source_output) for value in arguments]
        record["directory"] = replace_root(str(record["directory"]), args.source_output)
        record["file"] = replace_root(str(record["file"]), args.source_output)
        record["output"] = replace_root(str(record["output"]), args.source_output)
        output_records.append(record)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_records, indent=2) + "\n")
    print(json.dumps({
        "commands": len(output_records), "multicall_define": True,
        "production_sources": len(names), "selected_diagnostic_sources": args.only,
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
