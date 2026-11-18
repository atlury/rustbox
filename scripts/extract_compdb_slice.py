#!/usr/bin/env python3
"""Select compile commands by output-path regex without rewriting them."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def canonical(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-regex", required=True)
    parser.add_argument("--expected-commands", type=int)
    args = parser.parse_args()

    entries = json.loads(args.database.read_text(encoding="utf-8"))
    pattern = re.compile(args.output_regex)
    selected = [entry for entry in entries if pattern.search(entry.get("output", ""))]
    if not selected:
        raise RuntimeError(f"no compile commands match {args.output_regex!r}")
    if args.expected_commands is not None and len(selected) != args.expected_commands:
        raise RuntimeError(
            f"selected {len(selected)} compile commands, expected {args.expected_commands}"
        )
    if len({canonical(entry) for entry in selected}) != len(selected):
        raise RuntimeError("selected compile commands contain exact duplicates")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(selected, indent=2) + "\n", encoding="utf-8")
    summary = {
        "commands": len(selected),
        "sources": sorted({entry["file"] for entry in selected}),
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
