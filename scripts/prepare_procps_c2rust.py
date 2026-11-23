#!/usr/bin/env python3
"""Select one complete normalized C2Rust action per Procps production source."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
from collections import defaultdict
from pathlib import Path


SOURCE_ROOT = Path("/work/work/normalized/procps-ng-4.0.7")


def arguments(record: dict[str, object]) -> list[str]:
    values = record.get("arguments")
    if values is None:
        values = shlex.split(str(record["command"]))
    return [str(value) for value in values]


def preference(record: dict[str, object]) -> tuple[int, int, str]:
    args = arguments(record)
    feature_defines = sum(
        value in {"-D_DEFAULT_SOURCE", "-D_XOPEN_SOURCE=600"} for value in args
    )
    return (feature_defines, len(args), "\0".join(args))


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
    expected = set(oracle["production_closure"]["relative_paths"])
    if len(expected) != 49 or normalization["scope"]["entrypoint_engines"] != 17:
        raise RuntimeError("Procps verified source or entrypoint closure changed")

    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    excluded_test_actions = 0
    for original in records:
        source = (Path(original["directory"]) / str(original["file"])).resolve()
        if not source.is_relative_to(SOURCE_ROOT):
            raise RuntimeError(f"Procps compile action escapes normalized source: {source}")
        if "tests" in source.parts or "testsuite" in source.parts:
            excluded_test_actions += 1
            continue
        relative = source.relative_to(SOURCE_ROOT).as_posix()
        if relative not in expected:
            raise RuntimeError(f"unexpected Procps production source: {relative}")
        grouped[relative].append(dict(original))
    if set(grouped) != expected or excluded_test_actions != 3:
        raise RuntimeError(
            f"Procps C2Rust closure changed: excluded={excluded_test_actions}, "
            f"delta={sorted(set(grouped) ^ expected)}"
        )
    duplicate_actions = sum(len(items) - 1 for items in grouped.values())
    if duplicate_actions != 31:
        raise RuntimeError(f"Procps shared-source action count changed: {duplicate_actions}")

    output_records = []
    selected_variants = {}
    for relative in sorted(grouped):
        record = max(grouped[relative], key=preference)
        compile_args = arguments(record)
        if compile_args.count("-c") != 1:
            raise RuntimeError(f"malformed Procps compile action: {relative}")
        compile_args[compile_args.index("-c"):compile_args.index("-c")] = [
            "-DRUSTBOX_MULTICALL=1"
        ]
        record.pop("command", None)
        record["arguments"] = compile_args
        record["file"] = str(SOURCE_ROOT / relative)
        output_records.append(record)
        selected_variants[relative] = {
            "available_actions": len(grouped[relative]),
            "selected_default_source": "-D_DEFAULT_SOURCE" in compile_args,
            "selected_xopen_source_600": "-D_XOPEN_SOURCE=600" in compile_args,
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_records, indent=2) + "\n")
    variant_path = args.output.parent / "selected-variants.json"
    variant_path.write_text(json.dumps(selected_variants, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "commands": len(output_records),
        "duplicate_actions_collapsed": duplicate_actions,
        "excluded_test_actions": excluded_test_actions,
        "multicall_define": True,
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
