#!/usr/bin/env python3
"""Select Kmod's exact normalized 26-source production C2Rust closure."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
from pathlib import Path


SOURCE_ROOT = Path("/rustbox-kmod/normalized-source")
PRODUCTION_DIRECTORIES = {"shared", "libkmod", "tools"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--normalization", required=True, type=Path)
    parser.add_argument("--oracle", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    records = json.loads(args.database.read_text())
    normalization = json.loads(args.normalization.read_text())
    oracle = json.loads(args.oracle.read_text())
    expected = set(oracle["production_closure"]["relative_paths"])
    if normalization.get("changed_sources") != [
        "libkmod/libkmod-file.c", "libkmod/libkmod-module.c",
        "tools/depmod.c", "tools/kmod.c", "tools/modprobe.c",
        "tools/static-nodes.c",
    ]:
        raise RuntimeError("Kmod normalization source set changed")
    if normalization.get("entrypoint") != "rustbox_kmod_main":
        raise RuntimeError("Kmod multicall entrypoint changed")
    if len(expected) != 26:
        raise RuntimeError("Kmod oracle closure changed")

    selected: dict[str, dict[str, object]] = {}
    excluded_test_actions = 0
    for original in records:
        source = (Path(original["directory"]) / original["file"]).resolve()
        if source.parent.name not in PRODUCTION_DIRECTORIES:
            excluded_test_actions += 1
            continue
        relative = source.relative_to(SOURCE_ROOT).as_posix()
        if relative not in expected or relative in selected:
            raise RuntimeError(f"unexpected or duplicate Kmod production source: {relative}")
        record = dict(original)
        arguments = [str(value) for value in record.get(
            "arguments", shlex.split(str(record["command"]))
        )]
        if arguments.count("-c") != 1:
            raise RuntimeError(f"malformed Kmod compile action: {relative}")
        arguments[arguments.index("-c"):arguments.index("-c")] = [
            "-DRUSTBOX_MULTICALL=1"
        ]
        record.pop("command", None)
        record["arguments"] = arguments
        record["file"] = str(source)
        selected[relative] = record
    if set(selected) != expected or excluded_test_actions != 21:
        raise RuntimeError(
            f"Kmod C2Rust closure changed: excluded={excluded_test_actions}, "
            f"delta={sorted(set(selected) ^ expected)}"
        )

    output_records = [selected[name] for name in sorted(selected)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_records, indent=2) + "\n")
    print(json.dumps({
        "commands": len(output_records),
        "excluded_test_actions": excluded_test_actions,
        "multicall_define": True,
        "production_sources": len(expected),
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
