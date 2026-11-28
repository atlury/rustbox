// SPDX-License-Identifier: GPL-2.0-or-later
#![allow(non_camel_case_types)]
use core::ffi::{c_char, CStr};
use std::sync::OnceLock;
use libc::{closedir, fclose, fopen, fprintf, lstat, opendir, readdir, size_t, snprintf, strtoul, __errno_location, ENOENT};
unsafe extern "C" {
    static mut numeric: i32;
    static mut stderr: *mut libc::FILE;
    #[link_name = "rustbox_group_read"]
    fn fread_id_name(fp: *mut libc::FILE, id: *mut i32, name: *mut c_char) -> i32;
}
include!("../../compat/iproute2/route_tables.rs");
