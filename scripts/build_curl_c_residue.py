#!/usr/bin/env python3
"""Compile curl's canonical variadic long-double formatter boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


SOURCE = "lib/mprintf.c"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    records = json.loads(args.database.read_text())
    selected = [
        record for record in records
        if str(record["file"]).endswith("/" + SOURCE)
        and "-DUNITTESTS" not in record["arguments"]
    ]
    if len(records) != 477 or len(selected) != 1:
        raise RuntimeError("curl canonical C ABI residue closure changed")
    record = selected[0]
    arguments = list(record["arguments"])
    if arguments.count("-c") != 1 or arguments.count("-o") != 1:
        raise RuntimeError("malformed curl mprintf compile action")

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    object_path = output / "mprintf.o"
    arguments[arguments.index("-o") + 1] = str(object_path)
    subprocess.run(arguments, cwd=record["directory"], check=True)
    manifest = {
        "schema": 1,
        "sources": [{
            "source": SOURCE,
            "source_sha256": sha256(Path(record["file"])),
            "object": object_path.name,
            "object_sha256": sha256(object_path),
            "compiler": arguments[0],
            "unit_test_variant": False,
        }],
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({"objects": 1}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
