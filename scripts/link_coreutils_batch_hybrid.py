#!/usr/bin/env python3
"""Relink canonical Coreutils with one declared applet batch supplied by Rust."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path


SAFE_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
SAFE_APPLET = re.compile(r"^[A-Za-z0-9_-]+$")
SAFE_LINK_LIBRARY = re.compile(r"^-l[A-Za-z0-9_+.-]+$")


def make_assignment(path: Path, name: str) -> str:
    prefix = name + " = "
    matches = [
        line[len(prefix) :]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith(prefix)
    ]
    if len(matches) != 1:
        raise RuntimeError(f"expected one {name} assignment, found {len(matches)}")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--rust-library", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    build = args.build.resolve()
    rust_library = args.rust_library.resolve()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    batch = manifest.get("name")
    applets = manifest.get("applets")
    extra_link_libraries = manifest.get("extra_link_libraries", [])
    if not isinstance(batch, str) or not SAFE_NAME.fullmatch(batch):
        raise RuntimeError("batch manifest has an unsafe name")
    if (
        not isinstance(applets, list)
        or not applets
        or not all(isinstance(item, str) and SAFE_APPLET.fullmatch(item) for item in applets)
        or len(set(applets)) != len(applets)
    ):
        raise RuntimeError("batch manifest has invalid or duplicate applets")
    if (
        not isinstance(extra_link_libraries, list)
        or not all(
            isinstance(item, str) and SAFE_LINK_LIBRARY.fullmatch(item)
            for item in extra_link_libraries
        )
        or len(set(extra_link_libraries)) != len(extra_link_libraries)
    ):
        raise RuntimeError("batch manifest has invalid or duplicate extra link libraries")

    makefile = build / "Makefile"
    if not makefile.is_file() or not rust_library.is_file():
        raise RuntimeError("canonical build or generated Rust static library is missing")

    dependencies = make_assignment(makefile, "single_binary_deps").split()
    removed = {f"src/libsinglebin_{applet}.a" for applet in applets}
    for archive in sorted(removed):
        count = dependencies.count(archive)
        if count != 1:
            raise RuntimeError(f"expected one {archive} dependency, found {count}")

    rewritten: list[str] = []
    inserted = False
    for dependency in dependencies:
        if dependency in removed:
            if not inserted:
                rewritten.append(str(rust_library))
                inserted = True
        else:
            rewritten.append(dependency)

    output_name = f"coreutils-rust-{batch}"
    output = build / "src" / output_name
    link_map = output.with_suffix(".map")
    link = (
        "$(CCLD) $(src_coreutils_CFLAGS) $(CFLAGS) $(AM_LDFLAGS) "
        f"$(LDFLAGS) -Wl,-Map=src/{output_name}.map -o src/{output_name}"
    )
    command = [
        "make",
        "V=1",
        "src/coreutils",
        "single_binary_deps=" + " ".join(rewritten),
        "src_coreutils_LDADD=$(single_binary_deps) $(LDADD) $(single_binary_libs) "
        + " ".join(extra_link_libraries),
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

    if not output.is_file() or not link_map.is_file():
        raise RuntimeError("hybrid linker did not produce its isolated output")
    map_text = link_map.read_text(encoding="utf-8", errors="replace")
    if str(rust_library) not in map_text:
        raise RuntimeError("link map does not contain the generated Rust library")
    for archive in removed:
        # GNU's link variables can mention an archive again as support for a
        # different applet (notably uname for arch/hostname/uptime).  A LOAD
        # directive alone does not contribute code.  Reject any extracted
        # member, which GNU ld records as archive(member), and then verify the
        # final public entry point below.
        if archive + "(" in map_text:
            raise RuntimeError(f"link map contains a member from original {archive}")

    defined = subprocess.run(
        ["nm", "-g", "--defined-only", str(output)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    symbols = [line.split()[-1] for line in defined.splitlines() if line.split()]
    for applet in applets:
        symbol = "single_binary_main_" + applet.replace("-", "_")
        if symbols.count(symbol) != 1:
            raise RuntimeError(f"hybrid output does not define {symbol} exactly once")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
