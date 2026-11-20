#!/usr/bin/env python3
"""Create pkgconf's exact 35-source C2Rust compilation database."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
from pathlib import Path


PREFIXES = ("libpkgconf.a.p/", "pkgconf.p/", "bomtool.p/", "pccritic.p/", "spdxtool.p/")
ENTRYPOINTS = {
    "cli/main.c",
    "cli/bomtool/main.c",
    "cli/pccritic/main.c",
    "cli/spdxtool/main.c",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = json.loads(args.database.read_text())
    selected: dict[Path, dict[str, object]] = {}
    for original in records:
        if not str(original.get("output", "")).startswith(PREFIXES):
            continue
        source = (Path(original["directory"]) / original["file"]).resolve()
        if not source.is_relative_to(Path("/rustbox-pkgconf/normalized-source")):
            raise RuntimeError(f"pkgconf source escapes normalized tree: {source}")
        if source in selected:
            continue
        record = json.loads(json.dumps(original))
        command = shlex.split(record["command"])
        if command.count("-c") != 1:
            raise RuntimeError(f"malformed compile command: {source}")
        command.insert(command.index("-c"), "-DRUSTBOX_MULTICALL=1")
        record["command"] = shlex.join(command)
        record["file"] = str(source)
        selected[source] = record

    relative = {
        source.relative_to("/rustbox-pkgconf/normalized-source").as_posix()
        for source in selected
    }
    if len(selected) != 35 or not ENTRYPOINTS.issubset(relative):
        raise RuntimeError(
            f"pkgconf C2Rust closure changed: sources={len(selected)}, "
            f"entrypoints={sorted(ENTRYPOINTS & relative)}"
        )
    output_records = [selected[source] for source in sorted(selected)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_records, indent=2) + "\n")
    print(
        json.dumps(
            {
                "commands": len(output_records),
                "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                "multicall_define": True,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
