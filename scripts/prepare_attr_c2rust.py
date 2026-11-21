#!/usr/bin/env python3
"""Create attr's exact 21-source C2Rust compilation database."""

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
    source_root = Path("/rustbox-attr/normalized-source")
    selected: dict[Path, dict[str, object]] = {}
    relative_names: set[str] = set()
    for original in records:
        source = Path(original["file"]).resolve()
        if not source.is_relative_to(source_root):
            raise RuntimeError(f"attr source escapes normalized production closure: {source}")
        relative = source.relative_to(source_root).as_posix()
        if source in selected or relative in relative_names:
            raise RuntimeError(f"duplicate attr production action: {source}")
        record = json.loads(json.dumps(original))
        arguments = list(record["arguments"])
        if arguments.count("-c") != 1:
            raise RuntimeError(f"malformed attr compile command: {source}")
        arguments.insert(arguments.index("-c"), "-DRUSTBOX_MULTICALL=1")
        record["arguments"] = arguments
        record["file"] = str(source)
        selected[source] = record
        relative_names.add(relative)

    expected = {
        "libattr/attr_copy_action.c", "libattr/attr_copy_check.c",
        "libattr/attr_copy_fd.c", "libattr/attr_copy_file.c",
        "libattr/libattr.c", "libattr/syscalls.c",
        "libmisc/getxattrat_compat.c", "libmisc/high_water_alloc.c",
        "libmisc/listxattrat_compat.c", "libmisc/next_line.c",
        "libmisc/openat2.c", "libmisc/proc-self-fd.c", "libmisc/quote.c",
        "libmisc/removexattrat_compat.c", "libmisc/setxattrat_compat.c",
        "libmisc/unquote.c", "libmisc/walk_tree.c", "libmisc/xattrat.c",
        "tools/attr.c", "tools/getfattr.c", "tools/setfattr.c",
    }
    if len(records) != 21 or relative_names != expected:
        raise RuntimeError(f"attr C2Rust closure changed: {sorted(relative_names)}")
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
