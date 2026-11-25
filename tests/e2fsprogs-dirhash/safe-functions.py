#!/usr/bin/env python3
"""Compile the exact converted arithmetic functions with unsafe code forbidden and no lint cap."""
# SPDX-License-Identifier: GPL-2.0-only
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from check_e2fsprogs_dirhash_arrays import borrow_arrays


def check(translations):
    source, = (translations / "debugfs/debugfs-final").glob("**/lib/ext2fs/dirhash.rs")
    with tempfile.TemporaryDirectory() as tmp:
        module = Path(tmp) / "dirhash.rs"
        shutil.copyfile(source, module)
        if borrow_arrays(module) != 40:
            raise ValueError("expected both fixed-array helpers")
        data = module.read_bytes()
        start = data.index(b"pub const DELTA:")
        end = data.index(b'unsafe extern "C" fn dx_hack_hash(', start)
        standalone = Path(tmp) / "safe.rs"
        standalone.write_bytes(b"#![no_std]\ntype __u32 = u32;\n" + data[start:end])
        subprocess.run(["rustc", "+nightly-2023-04-15", "--edition=2021", "--crate-type=lib",
                        "--emit=metadata", "-A", "warnings", "-F", "unsafe-code", standalone],
                       cwd=tmp, check=True)
    print("Both directory hash transforms compiled with unsafe code forbidden.")


if __name__ == "__main__":
    check(Path(sys.argv[1]))
