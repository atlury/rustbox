#!/usr/bin/env python3
"""Create File's exact 25-source C2Rust compilation database."""

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
    records = json.loads(args.database.read_text())
    selected: dict[Path, dict[str, object]] = {}
    for original in records:
        source = Path(original["file"]).resolve()
        if not source.is_relative_to(Path("/rustbox-file/normalized-source/src")):
            raise RuntimeError(f"File source escapes normalized production tree: {source}")
        if source in selected:
            raise RuntimeError(f"duplicate File production action: {source}")
        record = json.loads(json.dumps(original))
        arguments = list(record["arguments"])
        if arguments.count("-c") != 1:
            raise RuntimeError(f"malformed File compile command: {source}")
        arguments.insert(arguments.index("-c"), "-DRUSTBOX_MULTICALL=1")
        record["arguments"] = arguments
        record["file"] = str(source)
        selected[source] = record

    relative = {
        source.relative_to("/rustbox-file/normalized-source").as_posix()
        for source in selected
    }
    if len(selected) != 25 or "src/file.c" not in relative or "src/magic.c" not in relative:
        raise RuntimeError(f"File C2Rust closure changed: {sorted(relative)}")
    output_records = [selected[source] for source in sorted(selected)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_records, indent=2) + "\n")
    print(json.dumps({
        "commands": len(output_records),
        "multicall_define": True,
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
