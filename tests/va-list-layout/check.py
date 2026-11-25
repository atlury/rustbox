#!/usr/bin/env python3
"""Compare layout and mixed argument cursors against independently compiled System V va_list users."""
# SPDX-License-Identifier: 0BSD
import json
from pathlib import Path
import subprocess
import sys
import tomllib
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from build_va_list_layout_pilot import TAG
from check_cargo_private_inlines import digest

here = Path(__file__).resolve().parent
with TemporaryDirectory() as tmp:
    directory = Path(tmp)
    (directory / "probe.rs").write_bytes(TAG + (here / "fields.rs").read_bytes())
    toolchain = tomllib.loads((ROOT / "rust-toolchain.toml").read_text())["toolchain"]["channel"]
    subprocess.run(["rustc", "+" + toolchain, "--edition=2021", "-O", "--crate-type=staticlib", "probe.rs", "-o", "probe.a"],
                   cwd=directory, check=True)
    results = {}
    for cc in ("gcc", "clang-18"):
        for level in ("-O0", "-O2"):
            subprocess.run([cc, level, "-Wall", "-Wextra", "-Werror", here / "abi.c", "probe.a", "-o", "probe"],
                           cwd=directory, check=True)
            values = list(map(int, subprocess.check_output([directory / "probe"]).split()))
            if values != [24, 8, 0, 4, 8, 16, 40]:
                raise ValueError(f"unexpected ABI measurements from {cc} {level}: {values}")
            results[cc + " " + level] = values
    print(json.dumps(dict(size_alignment_offsets_and_observations=results, c_driver_sha256=digest(here / "abi.c"),
                          rust_driver_sha256=digest(here / "fields.rs")), sort_keys=True))
