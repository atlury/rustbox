#!/usr/bin/env python3
"""Select the linked GNU M4 production closure from a Bear database."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-commands", type=int, default=192)
    args = parser.parse_args()

    records = json.loads(args.database.read_text())
    roots = (Path("/rustbox-m4/source/src"), Path("/rustbox-m4/source/lib"))
    selected = [
        record
        for record in records
        if any(Path(record["file"]).is_relative_to(root) for root in roots)
    ]
    if len(selected) != args.expected_commands:
        raise RuntimeError(
            f"selected {len(selected)} production commands, expected {args.expected_commands}"
        )
    files = [record["file"] for record in selected]
    if len(files) != len(set(files)):
        raise RuntimeError("production database contains repeated source configurations")
    application = [path for path in files if Path(path).is_relative_to(roots[0])]
    if len(application) != 11:
        raise RuntimeError(f"selected {len(application)} M4 application sources, expected 11")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(selected, indent=2) + "\n")
    print(json.dumps({"commands": len(selected), "application_sources": len(application)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
