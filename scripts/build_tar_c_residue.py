#!/usr/bin/env python3
"""Compile GNU tar's four canonical long-double/variadic ABI units."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


SOURCES = (
    "gnu/human.c",
    "gnu/printf-args.c",
    "gnu/printf-parse.c",
    "gnu/vasnprintf.c",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    records = json.loads(args.database.read_text())
    selected = {
        next(name for name in SOURCES if str(record["file"]).endswith("/" + name)):
        record
        for record in records
        if any(str(record["file"]).endswith("/" + name) for name in SOURCES)
    }
    if set(selected) != set(SOURCES):
        raise RuntimeError("GNU tar canonical C ABI residue closure changed")

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = []
    for source in SOURCES:
        record = selected[source]
        arguments = list(record["arguments"])
        if arguments.count("-c") != 1 or arguments.count("-o") != 1:
            raise RuntimeError(f"malformed compile action: {source}")
        object_path = output / (Path(source).stem + ".o")
        arguments[arguments.index("-o") + 1] = str(object_path)
        subprocess.run(arguments, cwd=record["directory"], check=True)
        manifest.append({
            "source": source,
            "source_sha256": sha256(Path(record["file"])),
            "object": object_path.name,
            "object_sha256": sha256(object_path),
            "compiler": arguments[0],
        })

    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps({
        "schema": 1,
        "sources": manifest,
    }, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"objects": len(manifest)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
