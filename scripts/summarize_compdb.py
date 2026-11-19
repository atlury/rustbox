#!/usr/bin/env python3
"""Validate a compile database without erasing per-configuration commands."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
from collections import Counter
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def contained(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--build-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compiler-family", choices=("clang", "gcc"), default="clang")
    args = parser.parse_args()

    database = args.database.resolve()
    source_root = args.source_root.resolve()
    build_root = args.build_root.resolve()
    entries = json.loads(database.read_text(encoding="utf-8"))
    if not isinstance(entries, list) or not entries:
        raise RuntimeError("compile database is empty or malformed")

    sources: Counter[str] = Counter()
    compilers: Counter[str] = Counter()
    locations: Counter[str] = Counter()
    command_digests: set[str] = set()
    for number, entry in enumerate(entries, 1):
        directory = Path(entry["directory"])
        if not directory.is_absolute() or not directory.is_dir():
            raise RuntimeError(f"entry {number}: invalid directory {directory}")
        source = Path(entry["file"])
        if not source.is_absolute():
            source = directory / source
        source = source.resolve()
        if not source.is_file():
            raise RuntimeError(f"entry {number}: missing source {source}")
        if contained(source, source_root):
            location = "canonical_source"
        elif contained(source, build_root):
            location = "generated_build"
        else:
            raise RuntimeError(f"entry {number}: source outside frozen roots: {source}")

        if "arguments" in entry:
            command = [str(value) for value in entry["arguments"]]
        elif "command" in entry:
            command = shlex.split(entry["command"])
        else:
            raise RuntimeError(f"entry {number}: no command or arguments")
        if not command:
            raise RuntimeError(f"entry {number}: empty command")
        compiler = os.path.basename(command[0])
        expected = {
            "clang": re.compile(r"^clang(?:-[0-9]+)?$"),
            "gcc": re.compile(r"^(?:gcc|cc)(?:-[0-9]+)?$"),
        }[args.compiler_family]
        if not expected.fullmatch(compiler):
            raise RuntimeError(f"entry {number}: unexpected compiler {compiler}")

        normalized_command = "\0".join([str(directory), *command]).encode()
        command_digests.add(hashlib.sha256(normalized_command).hexdigest())
        sources[str(source)] += 1
        compilers[compiler] += 1
        locations[location] += 1

    repeated = {source: count for source, count in sources.items() if count > 1}
    summary = {
        "schema": 1,
        "database_sha256": digest(database),
        "commands": len(entries),
        "distinct_commands": len(command_digests),
        "unique_translation_units": len(sources),
        "translation_units_with_multiple_configurations": len(repeated),
        "maximum_configurations_per_translation_unit": max(sources.values()),
        "locations": dict(sorted(locations.items())),
        "compilers": dict(sorted(compilers.items())),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
