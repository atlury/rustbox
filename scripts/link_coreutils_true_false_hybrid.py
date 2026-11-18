#!/usr/bin/env python3
"""Relink canonical Coreutils with only true/false supplied by generated Rust."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


def make_assignment(path: Path, name: str) -> str:
    prefix = name + " = "
    matches = [line[len(prefix) :] for line in path.read_text().splitlines() if line.startswith(prefix)]
    if len(matches) != 1:
        raise RuntimeError(f"expected one {name} assignment, found {len(matches)}")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--rust-library", type=Path, required=True)
    args = parser.parse_args()

    build = args.build.resolve()
    rust_library = args.rust_library.resolve()
    makefile = build / "Makefile"
    if not makefile.is_file() or not rust_library.is_file():
        raise RuntimeError("canonical build or generated Rust static library is missing")

    dependencies = make_assignment(makefile, "single_binary_deps").split()
    removed = {"src/libsinglebin_true.a", "src/libsinglebin_false.a"}
    if sum(dependency in removed for dependency in dependencies) != 2:
        raise RuntimeError("canonical true/false archives not found exactly once")
    rewritten: list[str] = []
    inserted = False
    for dependency in dependencies:
        if dependency in removed:
            if not inserted:
                rewritten.append(str(rust_library))
                inserted = True
        else:
            rewritten.append(dependency)

    link = (
        "$(CCLD) $(src_coreutils_CFLAGS) $(CFLAGS) $(AM_LDFLAGS) "
        "$(LDFLAGS) -Wl,-Map=src/coreutils-rust-true-false.map "
        "-o src/coreutils-rust-true-false"
    )
    command = [
        "make",
        "V=1",
        "src/coreutils",
        "single_binary_deps=" + " ".join(rewritten),
        "src_libsinglebin_false_a_ldadd=$(src_true_LDADD) -ldl -lpthread -lm -lrt -lutil",
        "src_coreutils_LINK=" + link,
    ]
    canonical = build / "src/coreutils"
    saved = build / "src/.coreutils-rustbox-canonical"
    if not canonical.is_file():
        subprocess.run(["make", "src/coreutils"], cwd=build, check=True)
    shutil.copy2(canonical, saved)
    os.utime(rust_library)
    try:
        subprocess.run(command, cwd=build, check=True)
    finally:
        os.replace(saved, canonical)

    output = build / "src/coreutils-rust-true-false"
    link_map = output.with_suffix(".map")
    if not output.is_file() or not link_map.is_file():
        raise RuntimeError("hybrid linker did not produce its isolated output")
    map_text = link_map.read_text(encoding="utf-8", errors="replace")
    if str(rust_library) not in map_text:
        raise RuntimeError("link map does not contain the generated Rust library")
    for archive in removed:
        if archive in map_text:
            raise RuntimeError(f"link map unexpectedly contains original {archive}")
    defined = subprocess.run(
        ["nm", "-g", "--defined-only", str(output)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    for symbol in ("single_binary_main_true", "single_binary_main_false", "true_mode"):
        if sum(line.split()[-1] == symbol for line in defined.splitlines()) != 1:
            raise RuntimeError(f"hybrid output does not define {symbol} exactly once")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
