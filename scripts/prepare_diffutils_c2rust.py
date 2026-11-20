#!/usr/bin/env python3
"""Create GNU Diffutils' exact 139-source C2Rust compilation database."""

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
    source_root = Path("/rustbox-diffutils/normalized-source")
    build_root = Path("/rustbox-diffutils/normalized-clang")
    selected: dict[Path, dict[str, object]] = {}
    relative_names: dict[Path, str] = {}
    for original in records:
        source = Path(original["file"]).resolve()
        if "/gnulib-tests/" in str(source):
            continue
        if source.is_relative_to(source_root):
            relative = source.relative_to(source_root).as_posix()
        elif source == build_root / "src/version.c":
            relative = "generated/src/version.c"
        else:
            raise RuntimeError(
                f"GNU Diffutils source escapes normalized production closure: {source}"
            )
        if source in selected or relative in relative_names.values():
            raise RuntimeError(f"duplicate GNU Diffutils production action: {source}")
        record = json.loads(json.dumps(original))
        arguments = list(record["arguments"])
        if arguments.count("-c") != 1:
            raise RuntimeError(f"malformed GNU Diffutils compile command: {source}")
        arguments.insert(arguments.index("-c"), "-DRUSTBOX_MULTICALL=1")
        record["arguments"] = arguments
        record["file"] = str(source)
        selected[source] = record
        relative_names[source] = relative

    relative = set(relative_names.values())
    expected_entrypoints = {"src/cmp.c", "src/diff.c", "src/diff3.c", "src/sdiff.c"}
    if (
        len(records) != 178
        or len(selected) != 139
        or len(relative) != 139
        or not expected_entrypoints.issubset(relative)
        or len([name for name in relative if name.startswith("lib/")]) != 124
        or len([name for name in relative if name.startswith("src/")]) != 14
        or relative & {"src/version.c"}
        or "generated/src/version.c" not in relative
    ):
        raise RuntimeError(f"GNU Diffutils C2Rust closure changed: {sorted(relative)}")
    output_records = [selected[source] for source in sorted(selected)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_records, indent=2) + "\n")
    print(
        json.dumps(
            {
                "commands": len(output_records),
                "multicall_define": True,
                "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
