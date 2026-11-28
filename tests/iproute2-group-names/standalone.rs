// SPDX-License-Identifier: GPL-2.0-or-later
#![allow(non_camel_case_types)]
use core::ffi::{c_char, c_int, c_long, c_void, CStr};
use std::sync::OnceLock;
type size_t = usize;
const ENOENT: i32 = 2;
unsafe extern "C" {
    static mut numeric: c_int;
    static mut stderr: *mut c_void;
    fn fopen(path: *const c_char, mode: *const c_char) -> *mut c_void;
    fn fclose(file: *mut c_void) -> c_int;
    fn fprintf(file: *mut c_void, fmt: *const c_char, ...) -> c_int;
    fn snprintf(buf: *mut c_char, size: usize, fmt: *const c_char, ...) -> c_int;
    fn __errno_location() -> *mut c_int;
    fn strtol(input: *const c_char, end: *mut *mut c_char, base: c_int) -> c_long;
    #[link_name="rustbox_group_read"]
    fn fread_id_name(file: *mut c_void, id: *mut c_int, name: *mut c_char) -> c_int;
}
include!("../../compat/iproute2/group_names.rs");
