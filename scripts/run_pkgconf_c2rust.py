#!/usr/bin/env python3
"""Run C2Rust over pkgconf's selected complete production closure."""

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
    if len(records) != 35 or len(sources) != 35:
        raise RuntimeError("pkgconf selected C2Rust closure is incomplete")
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
        "-I/rustbox-pkgconf/normalized-source",
        "-I/rustbox-pkgconf/normalized-source/cli",
        "-I/rustbox-pkgconf/normalized-source/cli/spdxtool",
        "-I/rustbox-pkgconf/normalized-clang-static",
        "-O2",
        "-g",
        "-fno-omit-frame-pointer",
        "-fPIC",
        "-std=c99",
        "-D_FILE_OFFSET_BITS=64",
        "-D_ATFILE_SOURCE",
        "-D_BSD_SOURCE",
        "-D_DARWIN_C_SOURCE",
        "-D_DEFAULT_SOURCE",
        "-D_POSIX_C_SOURCE=200809L",
        "-D_XOPEN_SOURCE=700",
        "-DLIBPKGCONF_EXPORT",
        "-DPKGCONFIG_IS_STATIC",
        "-DRUSTBOX_MULTICALL=1",
    ]
    subprocess.run(command, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
