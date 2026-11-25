"""Use the pinned Rust 2023 nightly's const CStr validator in place of newer c-string literal syntax."""
# SPDX-License-Identifier: GPL-3.0-or-later

MODE = "nightly-2023-04-15"
NAME = b"rustbox_checked_c_str"
FEATURE = b"#![feature(const_cstr_methods)]"
MACRO = b"""
macro_rules! rustbox_checked_c_str {
    ($bytes:literal) => {{
        const CHECKED: &::core::ffi::CStr = match ::core::ffi::CStr::from_bytes_with_nul($bytes) {
            Ok(value) => value,
            Err(_) => panic!("invalid C string"),
        };
        CHECKED
    }};
}
pub(crate) use rustbox_checked_c_str;
"""


def expression(spelling):
    # The common scanner has already parsed and compared both literals,
    # including every byte of the terminator and any non-UTF-8 escapes.
    end = spelling.rindex('"')
    return 'crate::rustbox_checked_c_str!(b' + spelling[1:end] + '\\0")' + spelling[end+1:]


def crate_root(original, source):
    if NAME in original or FEATURE in original or not original.startswith(b"#!["):
        raise ValueError("unexpected crate root for legacy C strings")
    return FEATURE + b" " + source + MACRO
