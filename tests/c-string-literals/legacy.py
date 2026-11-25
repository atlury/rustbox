#!/usr/bin/env python3
"""Run the crate-private C-string macro on the release's pinned pre-literal Rust compiler."""
# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from build_c_string_literal_pilot import rewrite
from legacy_checked_c_strings import MODE
from verify_c_string_sources import syntax_tool

with TemporaryDirectory(dir=ROOT / "work/analysis") as folder:
    crate = Path(folder)
    source = b'''#![forbid(unsafe_code)]
mod inner {
    pub const P: *const ::core::ffi::c_char = b"hi\\xff\\0" as *const u8 as *const ::core::ffi::c_char;
}
fn main() {
    let second = b"hi\\xff\\0" as *const u8 as *const ::core::ffi::c_char;
    assert!(!inner::P.is_null() && !second.is_null());
}
'''
    (crate / "lib.rs").write_bytes(source)
    checker = syntax_tool()
    (crate / "selected.rs").write_bytes(source)
    subset, subset_row = rewrite(crate, ["lib.rs", "selected.rs"], checker, MODE, ["selected.rs"])
    assert subset_row["modules"] == {"selected.rs": 2}
    assert source.split(b"mod inner", 1)[1] in subset["lib.rs"]
    assert subset["selected.rs"].count(b"crate::rustbox_checked_c_str!") == 2
    scoped = crate / "scoped"
    scoped.mkdir()
    (scoped / "main.rs").write_bytes(subset["lib.rs"] + b"\nmod selected;\n")
    (scoped / "selected.rs").write_bytes(subset["selected.rs"].replace(b"#![forbid(unsafe_code)]", b""))

    changed, row = rewrite(crate, ["lib.rs"], checker, MODE)
    assert row["raw_pointer_types_removed"] == 4 and row["raw_ffi_pointer_extractions"] == 2
    body = changed["lib.rs"]
    (crate / "positive.rs").write_bytes(body)
    for name, bad in (("interior", b'hi\\0x\\0'), ("missing", b'hi')):
        (crate / (name + ".rs")).write_bytes(body.replace(b'hi\\xff\\0', bad))
    command = """set -eu
cd /tmp
for unit in lib positive; do
    rustc +nightly-2023-04-15 --edition=2021 /src/$unit.rs -o "$unit"
    "./$unit"
done
rustc +nightly-2023-04-15 -A warnings --edition=2021 /src/scoped/main.rs -o scoped
./scoped
for unit in interior missing; do
    if rustc +nightly-2023-04-15 --edition=2021 /src/$unit.rs -o "$unit" 2> "$unit.log"; then exit 1; fi
    grep -q 'E0080' "$unit.log"
    grep -q 'invalid C string' "$unit.log"
done"""
    subprocess.run(["docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64", "-v",
                    f"{crate}:/src:ro", "rustbox-e2fsprogs:2026-11-24", "sh", "-c", command], check=True)
print("The pinned nightly accepted both valid forms and rejected the embedded and missing terminators at compile time.")
