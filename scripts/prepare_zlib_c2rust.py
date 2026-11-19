#!/usr/bin/env python3
"""Select one exact production command per zlib source for C2Rust."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    database = json.loads(args.database.read_text())
    build = args.database.parent
    source = build.parent / "source"
    selected = []
    for record in database:
        file = Path(record["file"])
        output = Path(record["output"])
        if file.parent.name == "source" and output.parent.name == "clang-make":
            selected.append(record)
    selected.sort(key=lambda record: Path(record["file"]).name)
    names = [Path(record["file"]).name for record in selected]
    expected = sorted(path.name for path in source.glob("*.c"))
    if names != expected or len(selected) != 15 or len(set(names)) != 15:
        raise RuntimeError(f"expected one command for each production source: {names!r}")
    expected_flags = [
        "-O2", "-g", "-fno-omit-frame-pointer", "-fPIC",
        "-D_LARGEFILE64_SOURCE=1", "-DHAVE_HIDDEN", "-I.",
        "-include", "zconf.h",
    ]
    for record in selected:
        arguments = record["arguments"]
        compile_index = arguments.index("-c")
        if arguments[1:compile_index] != expected_flags:
            raise RuntimeError(f"unexpected production flags: {record['file']}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(selected, indent=2) + "\n"
    args.output.write_text(data)
    print(json.dumps({
        "commands": len(selected),
        "common_flags": expected_flags,
        "sha256": hashlib.sha256(data.encode()).hexdigest(),
        "sources": names,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
