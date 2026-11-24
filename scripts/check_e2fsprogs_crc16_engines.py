#!/usr/bin/env python3
"""Rebuild each generated CRC16 consumer against a single Rustbox checksum object."""
# SPDX-License-Identifier: GPL-2.0-only

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import tempfile
from build_e2fsprogs_checksums import CONSUMERS, build_archive

REPO = Path(__file__).resolve().parents[1]


def build(name, translations, output, checksum):
    with tempfile.TemporaryDirectory() as scratch:
        archive = build_archive(name, translations, Path(scratch) / "engine.a", shared=False)
        binary = output / name
        subprocess.run(["clang-18", "-O2", "-Wl,--gc-sections",
                        f"-DRUSTBOX_E2FSPROGS_ENTRY=rustbox_e2fsprogs_{name}_main",
                        REPO / "bridges/e2fsprogs_program_main.c", archive, checksum,
                        "-lblkid", "-luuid", "-lfuse3", "-ldl", "-lpthread", "-lm",
                        "-o", binary], check=True)
        return name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("translations", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("checksum", type=Path)
    parser.add_argument("--all-engines", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    checksum = args.checksum.resolve()
    translations = args.translations.resolve()
    selected = ["e2fsck"]
    if args.all_engines:
        selected = sorted(p.parent.name for p in translations.glob("*/*-final")
                          if any(p.glob("**/lib/ext2fs/crc16.rs")))
        if tuple(selected) != CONSUMERS:
            raise ValueError(f"unexpected set of checksum consumers: {selected}")
    output.mkdir()
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = [executor.submit(build, name, translations, output, checksum) for name in selected]
        for result in results:
            print(f"Linked {result.result()} to the shared CRC16 object", flush=True)
    if args.all_engines:
        # Preserve public aliases and previously verified, unaffected engines for
        # the existing full 28-name differential command suite.
        originals = Path("/rustbox-e2fsprogs/program-hybrids")
        for path in originals.iterdir():
            if path.name in selected:
                continue
            (output / path.name).symlink_to(path.readlink() if path.is_symlink() else path)


if __name__ == "__main__":
    main()
