#!/usr/bin/env python3
"""Create the exact 11-source GNU M4 C2Rust compilation database."""

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
    prefix = "/rustbox-m4/normalized-source/src/"
    selected = []
    for original in records:
        if not original["file"].startswith(prefix):
            continue
        record = json.loads(json.dumps(original))
        arguments = record.get("arguments")
        if not arguments or arguments.count("-c") != 1:
            raise RuntimeError(f"malformed compile command: {record['file']}")
        arguments.insert(arguments.index("-c"), "-DRUSTBOX_MULTICALL=1")
        selected.append(record)
    if len(selected) != 11 or len({record["file"] for record in selected}) != 11:
        raise RuntimeError(f"expected 11 unique M4 sources, found {len(selected)}")
    if not any(record["file"].endswith("/m4.c") for record in selected):
        raise RuntimeError("M4 entrypoint source is absent")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(selected, indent=2) + "\n")
    print(json.dumps({
        "commands": len(selected),
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "multicall_define": True,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
