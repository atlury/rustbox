#!/usr/bin/env python3
"""Run C2Rust over File's selected complete production closure."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = json.loads(args.database.read_text())
    sources = sorted({record["file"] for record in records})
    if len(records) != 25 or len(sources) != 25:
        raise RuntimeError("File selected C2Rust closure is incomplete")
    command = [
        "c2rust",
        "transpile",
        "--output-dir",
        str(args.output),
        "--emit-build-files",
        "--emit-c-decl-map",
        "--fail-on-error",
        "--disable-rustfmt",
        "--overwrite-existing",
        "--preserve-unused-functions",
        *sources,
        "--",
        "-DHAVE_CONFIG_H",
        "-DRUSTBOX_MULTICALL=1",
        '-DMAGIC="/usr/local/share/misc/magic"',
        "-I/rustbox-file/normalized-source/src",
        "-I/rustbox-file/normalized-clang",
        "-I/rustbox-file/normalized-clang/src",
        "-O2",
        "-g",
        "-fno-omit-frame-pointer",
        "-fvisibility=hidden",
    ]
    subprocess.run(command, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
