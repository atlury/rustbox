"""Expose the exact private Rust leaf adapter to the C scratch-buffer comparison."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from e2fsprogs_hangul import NEW_CALL, RUST

Path("adapter.rs").write_bytes(b"#![no_std]\n" + RUST.read_bytes() + b"""
#[no_mangle]
pub unsafe extern "C" fn rust_leaf(s: *const u8, hangul: *mut u8) -> *const u8 {
    let trie;
""" + NEW_CALL + b"\n    trie\n}\n")
