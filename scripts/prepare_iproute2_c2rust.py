#!/usr/bin/env python3
"""Select one strict C2Rust action per normalized IPRoute2 utility source."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
from collections import defaultdict
from pathlib import Path


SOURCE_ROOT = Path("/rustbox-iproute2/normalized-clang-18")
EXCLUDED_BUILD_HELPERS = {
    "netem/maketable.c", "netem/normal.c", "netem/pareto.c",
    "netem/paretonormal.c",
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
    if (
        oracle["scope"]["production_utility_sources"] != 260
        or normalization["scope"]["exported_native_engines"] != 18
    ):
        raise RuntimeError("IPRoute2 verified source or entrypoint closure changed")

    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    excluded = set()
    for original in records:
        source = (Path(original["directory"]) / str(original["file"])).resolve()
        if not source.is_relative_to(SOURCE_ROOT):
            raise RuntimeError(f"IPRoute2 compile action escapes normalized source: {source}")
        relative = source.relative_to(SOURCE_ROOT).as_posix()
        if relative in EXCLUDED_BUILD_HELPERS:
            excluded.add(relative)
            continue
        grouped[relative].append(dict(original))
    if excluded != EXCLUDED_BUILD_HELPERS or len(grouped) != 260:
        raise RuntimeError(
            f"IPRoute2 C2Rust closure changed: excluded={sorted(excluded)}, "
            f"sources={len(grouped)}"
        )

    output_records = []
    variants = {}
    for relative in sorted(grouped):
        candidates = grouped[relative]
        record = max(
            candidates,
            key=lambda item: (
                int("-c" in arguments(item)),
                len(arguments(item)),
                "\0".join(arguments(item)),
            ),
        )
        compile_args = arguments(record)
        if compile_args.count("-c") != 1:
            raise RuntimeError(f"malformed IPRoute2 compile action: {relative}")
        compile_args[compile_args.index("-c"):compile_args.index("-c")] = [
            "-DRUSTBOX_MULTICALL=1"
        ]
        record.pop("command", None)
        record["arguments"] = compile_args
        record["file"] = str(SOURCE_ROOT / relative)
        output_records.append(record)
        variants[relative] = len(candidates)

    duplicate_actions = sum(count - 1 for count in variants.values())
    if duplicate_actions != 4:
        raise RuntimeError(f"IPRoute2 duplicate action inventory changed: {duplicate_actions}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_records, indent=2) + "\n")
    manifest = {
        "schema": 1,
        "commands": len(output_records),
        "excluded_build_helpers": sorted(EXCLUDED_BUILD_HELPERS),
        "duplicate_actions_collapsed": duplicate_actions,
        "multicall_define": True,
        "variants": variants,
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }
    (args.output.parent / "closure.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({
        "commands": len(output_records),
        "duplicate_actions_collapsed": duplicate_actions,
        "excluded_build_helpers": len(excluded),
        "sha256": manifest["sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
