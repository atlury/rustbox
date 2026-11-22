#!/usr/bin/env python3
"""Select Flex's final production closure for strict C2Rust translation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--normalization", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.normalization.read_text())
    if manifest["changed_sources"] != ["src/main.c"]:
        raise RuntimeError("Flex normalization source set changed")
    records = json.loads(args.database.read_text())
    if len(records) != 46:
        raise RuntimeError("Flex normalized compile database changed")

    selected = []
    for record in records:
        output = Path(record.get("output", "")).name
        if not output.startswith("flex-"):
            continue
        if output in {"flex-libmain.o", "flex-libyywrap.o"}:
            continue
        arguments = list(record["arguments"])
        if "-DRUSTBOX_MULTICALL" not in arguments:
            arguments.insert(1, "-DRUSTBOX_MULTICALL")
        updated = dict(record)
        updated["arguments"] = arguments
        selected.append(updated)

    sources = sorted({record["file"] for record in selected})
    if len(selected) != 21 or len(sources) != 21:
        raise RuntimeError(f"Flex final production closure changed: {len(selected)}/{len(sources)}")
    if sum(source.endswith("/src/stage1scan.c") for source in sources) != 1:
        raise RuntimeError("Flex generated final scanner source changed")
    if sum(source.startswith("/rustbox-flex/normalized-source/src/") for source in sources) != 20:
        raise RuntimeError("Flex normalized final source set changed")
    if not any(source.endswith("/src/main.c") for source in sources):
        raise RuntimeError("Flex multicall entrypoint source is absent")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(selected, indent=2) + "\n")
    print(json.dumps({
        "commands": len(selected), "generated_sources": 1,
        "normalized_sources": 20, "sources": len(sources),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
