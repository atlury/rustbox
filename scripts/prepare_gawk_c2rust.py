#!/usr/bin/env python3
"""Create GNU Gawk's exact full-feature C2Rust database."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SOURCE_ROOT = Path("/rustbox-gawk/normalized-source")
GENERATED_ROOT = Path("/rustbox-gawk/normalized-clang/awklib")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--normalization", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = json.loads(args.database.read_text())
    normalization = json.loads(args.normalization.read_text())
    if normalization.get("entrypoints") != 1 or normalization.get("changed_sources") != [
        "extension/readdir.c", "main.c", "support/pma.c",
    ]:
        raise RuntimeError("GNU Gawk normalization manifest changed")
    if len(records) != 55:
        raise RuntimeError("GNU Gawk Clang compile-action count changed")

    selected = []
    names = []
    for original in records:
        source = Path(str(original["file"])).resolve()
        if source.is_relative_to(SOURCE_ROOT):
            relative = source.relative_to(SOURCE_ROOT).as_posix()
        elif source.is_relative_to(GENERATED_ROOT):
            relative = "generated/" + source.relative_to(GENERATED_ROOT).as_posix()
        else:
            raise RuntimeError(f"GNU Gawk source escapes normalized closure: {source}")
        names.append(relative)
        record = json.loads(json.dumps(original))
        arguments = list(record["arguments"])
        recorded_source = Path(str(original["file"]))
        if recorded_source.is_relative_to(GENERATED_ROOT):
            resolved = recorded_source.resolve()
            arguments = [str(resolved) if item == str(recorded_source) else item
                         for item in arguments]
            record["file"] = str(resolved)
        if arguments.count("-c") != 1:
            raise RuntimeError(f"malformed GNU Gawk compile action: {relative}")
        arguments.insert(arguments.index("-c"), "-DRUSTBOX_MULTICALL=1")
        record["arguments"] = arguments
        selected.append(record)
    if len(names) != len(set(names)):
        raise RuntimeError("duplicate GNU Gawk production action")
    closure = hashlib.sha256(("\n".join(sorted(names)) + "\n").encode()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(selected, indent=2) + "\n")
    print(json.dumps({
        "commands": len(selected), "multicall_define": True,
        "production_closure_sha256": closure,
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
