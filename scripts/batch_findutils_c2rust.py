#!/usr/bin/env python3
"""Split the pinned Findutils database into bounded deterministic batches."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


BATCH_SIZE = 32
SINGLETON_SOURCES = {"/gl/lib/parse-datetime.c"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    records = json.loads(args.database.read_text())
    if len(records) != 193:
        raise RuntimeError("Findutils production database changed")
    if args.output_dir.exists():
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True)

    grouped: list[list[dict[str, object]]] = []
    pending: list[dict[str, object]] = []
    for record in records:
        source = str(record["file"])
        if any(source.endswith(suffix) for suffix in SINGLETON_SOURCES):
            if pending:
                grouped.append(pending)
                pending = []
            grouped.append([record])
        else:
            pending.append(record)
            if len(pending) == BATCH_SIZE:
                grouped.append(pending)
                pending = []
    if pending:
        grouped.append(pending)

    batches = []
    for index, batch in enumerate(grouped):
        directory = args.output_dir / f"batch-{index:03d}"
        directory.mkdir()
        database = directory / "compile_commands.json"
        database.write_text(json.dumps(batch, indent=2) + "\n")
        batches.append({
            "batch": index,
            "commands": len(batch),
            "first_source": batch[0]["file"],
            "last_source": batch[-1]["file"],
            "sha256": hashlib.sha256(database.read_bytes()).hexdigest(),
        })
    manifest = {
        "schema": 1,
        "batch_size": BATCH_SIZE,
        "singleton_sources": sorted(SINGLETON_SOURCES),
        "declaration_map_exceptions": sorted(SINGLETON_SOURCES),
        "batches": batches,
        "commands": sum(batch["commands"] for batch in batches),
        "reason": (
            "C2Rust 0.22.1 corrupts declaration-map source offsets for Bison-generated "
            "parse-datetime.c; strict translation succeeds without that optional map, so its "
            "singleton batch isolates the metadata exception while all code is preserved"
        ),
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({
        "batch_size": BATCH_SIZE,
        "batches": len(batches),
        "commands": manifest["commands"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
