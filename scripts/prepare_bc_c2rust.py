#!/usr/bin/env python3
"""Create GNU bc's exact 21-source C2Rust compilation database."""

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
    source_root = Path("/rustbox-bc/normalized-source")
    selected: dict[Path, dict[str, object]] = {}
    relative_names: set[str] = set()
    for original in records:
        source = Path(original["file"]).resolve()
        if not source.is_relative_to(source_root):
            raise RuntimeError(f"GNU bc source escapes normalized production closure: {source}")
        relative = source.relative_to(source_root).as_posix()
        if source in selected or relative in relative_names:
            raise RuntimeError(f"duplicate GNU bc production action: {source}")
        record = json.loads(json.dumps(original))
        arguments = list(record["arguments"])
        if arguments.count("-c") != 1:
            raise RuntimeError(f"malformed GNU bc compile command: {source}")
        arguments.insert(arguments.index("-c"), "-DRUSTBOX_MULTICALL=1")
        record["arguments"] = arguments
        record["file"] = str(source)
        selected[source] = record
        relative_names.add(relative)

    expected = {
        "bc/bc.c", "bc/execute.c", "bc/global.c", "bc/load.c", "bc/main.c",
        "bc/scan.c", "bc/storage.c", "bc/util.c", "bc/warranty.c",
        "dc/array.c", "dc/dc.c", "dc/eval.c", "dc/input.c", "dc/misc.c",
        "dc/numeric.c", "dc/stack.c", "dc/string.c",
        "lib/getopt.c", "lib/getopt1.c", "lib/number.c", "lib/vfprintf.c",
    }
    if len(records) != 21 or relative_names != expected:
        raise RuntimeError(f"GNU bc C2Rust closure changed: {sorted(relative_names)}")
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
