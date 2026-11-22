#!/usr/bin/env python3
"""Split the pinned GNU Gawk database into bounded C2Rust batches."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


BATCH_SIZE = 16
SINGLETON_SUFFIXES = ("/awkgram.c", "/command.c")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    records = json.loads(args.database.read_text())
    if len(records) != 55:
        raise RuntimeError("GNU Gawk production database changed")
    if args.output_dir.exists():
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True)
    grouped = []
    pending = []
    for record in records:
        if str(record["file"]).endswith(SINGLETON_SUFFIXES):
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
            "batch": index, "commands": len(batch),
            "first_source": batch[0]["file"], "last_source": batch[-1]["file"],
            "sha256": hashlib.sha256(database.read_bytes()).hexdigest(),
        })
    manifest = {"schema": 1, "batch_size": BATCH_SIZE, "commands": len(records),
                "singleton_sources": list(SINGLETON_SUFFIXES),
                "declaration_map_exceptions": list(SINGLETON_SUFFIXES),
                "batches": batches}
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({"batch_size": BATCH_SIZE, "batches": len(batches),
                      "commands": len(records)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
