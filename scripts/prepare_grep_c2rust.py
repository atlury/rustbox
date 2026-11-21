#!/usr/bin/env python3
"""Create GNU Grep's exact 129-source C2Rust compilation database."""

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
    source_root = Path("/rustbox-grep/normalized-source")
    build_root = Path("/rustbox-grep/normalized-clang")
    selected: dict[Path, dict[str, object]] = {}
    relative_names: dict[Path, str] = {}
    for original in records:
        source = Path(original["file"]).resolve()
        if "/gnulib-tests/" in str(source):
            continue
        if source.is_relative_to(source_root):
            relative = source.relative_to(source_root).as_posix()
        elif source == build_root / "lib/colorize.c":
            relative = "generated/lib/colorize.c"
        else:
            raise RuntimeError(f"GNU Grep source escapes normalized production closure: {source}")
        if source in selected or relative in relative_names.values():
            raise RuntimeError(f"duplicate GNU Grep production action: {source}")
        record = json.loads(json.dumps(original))
        arguments = list(record["arguments"])
        if arguments.count("-c") != 1:
            raise RuntimeError(f"malformed GNU Grep compile command: {source}")
        arguments.insert(arguments.index("-c"), "-DRUSTBOX_MULTICALL=1")
        record["arguments"] = arguments
        record["file"] = str(source)
        selected[source] = record
        relative_names[source] = relative

    relative = set(relative_names.values())
    if (
        len(records) != 169
        or len(selected) != 129
        or len(relative) != 129
        or "src/grep.c" not in relative
        or len([name for name in relative if name.startswith("lib/")]) != 122
        or len([name for name in relative if name.startswith("src/")]) != 6
        or relative & {"lib/colorize.c"}
        or "generated/lib/colorize.c" not in relative
    ):
        raise RuntimeError(f"GNU Grep C2Rust closure changed: {sorted(relative)}")
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
