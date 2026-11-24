#!/usr/bin/env python3
"""Rebuild each generated CRC16 consumer against a single Rustbox checksum object."""
# SPDX-License-Identifier: GPL-2.0-only

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib

REPO = Path(__file__).resolve().parents[1]
CRC16_MODULE_SHA = "c3e5eff63f35648b28420174e58a0646ab5ec29d93e9d37321c5f557beed45cd"


def build(name, translations, output, checksum):
    source = translations / name / f"{name}-final"
    deps = translations / "cargo-target" / name / "release/deps"
    with tempfile.TemporaryDirectory() as scratch:
        engine = Path(scratch) / name
        shutil.copytree(source, engine, ignore=shutil.ignore_patterns("target"))
        module, = engine.glob("**/lib/ext2fs/crc16.rs")
        if hashlib.sha256(module.read_bytes()).hexdigest() != CRC16_MODULE_SHA:
            raise ValueError(f"CRC16 translation changed in {name}")
        module.write_text("// ext2fs_crc16 is supplied by the Rustbox checksum object.\n")
        crate = tomllib.loads((engine / "Cargo.toml").read_text())
        args = ["rustc", "+nightly-2023-04-15", "--edition=2021", "--crate-type=staticlib",
                "--crate-name", crate["lib"]["name"], "-C", "opt-level=3", "--cap-lints=allow",
                "--remap-path-prefix", f"{scratch}=/rustbox-e2fsprogs",
                "-L", f"dependency={deps}"]
        for dependency in crate["dependencies"]:
            rust_name = dependency.replace("-", "_")
            library, = deps.glob(f"lib{rust_name}-*.rlib")
            args.extend(["--extern", f"{rust_name}={library}"])
        archive = engine / "engine.a"
        subprocess.run([*args, "lib.rs", "-o", archive], cwd=engine, check=True)
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
        if len(selected) != 13 or "e2fsck" not in selected:
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
