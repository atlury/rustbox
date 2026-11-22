#!/usr/bin/env python3
"""Create GNU Findutils' exact 193-source installed-runtime C2Rust database."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SOURCE_ROOT = Path("/work/work/normalized/findutils-4.10.0")
EXPECTED_CLOSURE = "d5375c42acf093b50f488674802cf26b386202ae993a44f00ceeaff2a8c63dbb"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--normalization", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--only", action="append", default=[])
    args = parser.parse_args()
    records = json.loads(args.database.read_text())
    normalization = json.loads(args.normalization.read_text())
    if (
        normalization.get("entrypoints") != 4
        or len(normalization.get("changed_sources", [])) != 4
    ):
        raise RuntimeError("Findutils normalization manifest changed")
    if len(records) != 218:
        raise RuntimeError("Findutils Clang compile-action count changed")

    selected: dict[str, dict[str, object]] = {}
    test_sources: list[str] = []
    build_helpers: list[str] = []
    for original in records:
        source = Path(str(original["file"])).resolve()
        if not source.is_relative_to(SOURCE_ROOT):
            raise RuntimeError(f"Findutils source escapes normalized closure: {source}")
        relative = source.relative_to(SOURCE_ROOT).as_posix()
        if relative.startswith("gnulib-tests/"):
            test_sources.append(relative)
            continue
        if relative == "find/getlimits.c":
            build_helpers.append(relative)
            continue
        if relative in selected:
            raise RuntimeError(f"duplicate Findutils production action: {relative}")
        selected[relative] = original

    names = sorted(selected)
    closure = hashlib.sha256(("\n".join(names) + "\n").encode()).hexdigest()
    groups: dict[str, int] = {}
    for name in names:
        group = name.split("/", 1)[0]
        groups[group] = groups.get(group, 0) + 1
    expected_groups = {"find": 10, "gl": 167, "lib": 12, "locate": 3, "xargs": 1}
    if (
        len(names) != 193
        or len(test_sources) != 24
        or build_helpers != ["find/getlimits.c"]
        or closure != EXPECTED_CLOSURE
        or groups != expected_groups
    ):
        raise RuntimeError("Findutils production C2Rust closure changed")

    requested = set(args.only)
    if requested and not requested <= set(names):
        raise RuntimeError(f"unknown Findutils diagnostic source: {sorted(requested - set(names))}")
    output_records: list[dict[str, object]] = []
    for relative in sorted(requested or set(names)):
        record = json.loads(json.dumps(selected[relative]))
        arguments = list(record["arguments"])
        if arguments.count("-c") != 1:
            raise RuntimeError(f"malformed Findutils compile action: {relative}")
        arguments.insert(arguments.index("-c"), "-DRUSTBOX_MULTICALL=1")
        record["arguments"] = arguments
        output_records.append(record)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_records, indent=2) + "\n")
    print(json.dumps({
        "commands": len(output_records),
        "excluded_build_helpers": build_helpers,
        "excluded_test_sources": len(test_sources),
        "groups": groups,
        "multicall_define": True,
        "production_closure_sha256": closure,
        "selected_diagnostic_sources": args.only,
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
