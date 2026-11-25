#!/usr/bin/env python3
"""Borrow the two caller-owned timestamps in GNU tar's translated validate_timespec."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from hashlib import sha256
from pathlib import Path
import re

from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import LINK_REPORT
from prune_private_inlines import POINTER

MODULE = "src/gnu/utimens.rs"
ARCHIVE = "work/analysis/tar-1.35/translations/c2rust-0.22.1/tar-1.35-stable/target/release/libtar_1_35_normalized_audit.a"
MARKER = ".rustbox-tar-timespec-pilot"
FUNCTIONS = {
    b'unsafe extern "C" fn validate_timespec(': "21077fe22a0029e8ca6a8bf889137ba906e44907921031f961910e7c6ed3ad8a",
    b'pub unsafe extern "C" fn fdutimens(': "3d1e2bd8792b88c0c14ed703e2fbc215ba309a884c924af670883acd27919917",
    b'pub unsafe extern "C" fn lutimens(': "095fb90c162d7984f8ec7f309eaf877670da64293d63b8d688d23faf485f4a7c",
}
POINTER_INIT = b"""    let mut ts: *mut timespec = if !timespec.is_null() {
        &raw mut adjusted_timespec as *mut timespec
    } else {
        ::core::ptr::null_mut::<timespec>()
    };
"""
NEW_POINTER_INIT = b"""    let mut ts = if timespec.is_null() {
        ::core::ptr::null_mut::<timespec>()
    } else {
        adjusted_timespec.as_mut_ptr()
    };
"""
CHECK = b"    if adjustment_needed < 0 as ::core::ffi::c_int {\n"


def substitute(crate, sources):
    path = crate / MODULE
    original = data = path.read_bytes()
    if MODULE not in sources or data.count(b"validate_timespec(") != 3:
        raise ValueError("unexpected compiler module or caller set")
    accesses = 0
    for start, checksum in FUNCTIONS.items():
        i = data.index(start)
        j = data.index(b"\n}\n", i) + 3
        function = data[i:j]
        if sha256(function).hexdigest() != checksum:
            raise ValueError(f"unrecognized timestamp function: {start!r}")
        if start.startswith(b"unsafe"):
            function = function.replace(start, b"#[forbid(unsafe_code)]\nfn validate_timespec(")
            function = function.replace(b"mut timespec: *mut timespec,", b"timespec: &mut [timespec; 2],")
            function = function.replace(b"        *__errno_location() = EINVAL;\n", b"")
            function, accesses = re.subn(rb"\(\*timespec\.offset\(([01]) as ::core::ffi::c_int as isize\)\)",
                                      rb"timespec[\1]", function)
            if accesses != 16 or POINTER.search(function) or b".offset(" in function:
                raise ValueError("incomplete timestamp borrow")
        else:
            # Both public functions copy both input timestamps into their own
            # array before validation. Derive the syscall pointer after its
            # exclusive borrow ends, retaining the original null-input path.
            function = function.replace(POINTER_INIT, b"")
            function = function.replace(b"if !ts.is_null()", b"if !timespec.is_null()", 1)
            function = function.replace(b"validate_timespec(ts as *mut timespec)", b"validate_timespec(&mut adjusted_timespec)")
            function = function.replace(CHECK, NEW_POINTER_INIT + CHECK + b"        *__errno_location() = EINVAL;\n")
        data = data[:i] + function + data[j:]
    return {MODULE: data}, dict(module=MODULE, raw_offset_accesses_replaced=accesses, safe_helpers=1, callers=2,
        raw_pointer_types_removed=len(POINTER.findall(original))-len(POINTER.findall(data)),
        control_module_sha256=sha256(original).hexdigest(), candidate_module_sha256=sha256(data).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--link", type=Path, default=LINK_REPORT)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path)
    mode.add_argument("--mounted", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.mounted:
        compile_mounted_sources(args.mounted, substitute, MARKER, allow_identical=True)
    else:
        stage_selected_archive(args.link, args.output.resolve(), ARCHIVE, MARKER, Path(__file__).name)
