// SPDX-License-Identifier: GPL-2.0-or-later
#![no_std]
#![deny(unsafe_op_in_unsafe_fn)]

mod rtattr;

use core::ffi::{c_char, c_int, c_void};
use core::ptr::NonNull;

#[repr(C)]
pub struct Attribute {
    len: u16,
    kind: u16,
}

unsafe extern "C" {
    static mut stderr: *mut c_void;
    fn fprintf(stream: *mut c_void, format: *const c_char, ...) -> c_int;
}

/// # Safety
/// Matches the IPRoute2 7.3.0 Linux ABI. The caller provides a disjoint,
/// writable table of max+1 pointers (-1 means an empty table) and stable
/// input storage containing the initialized header fields that C reads.
/// When residual length is nonzero the canonical diagnostic also requires
/// a readable length field at the final aligned cursor. The logical length
/// alone does not guarantee backing for that diagnostic.
#[no_mangle]
pub unsafe extern "C" fn parse_rtattr_flags(
    table: *mut *mut Attribute,
    max: c_int,
    input: *mut Attribute,
    len: c_int,
    flags: u16,
) -> c_int {
    let slots = if max < 0 {
        &mut [][..]
    } else {
        let count = max as usize + 1;
        // Option<NonNull<T>> has pointer layout and all-zero represents None.
        // Initialize the output before creating a reference to caller storage.
        let base = table.cast::<Option<NonNull<Attribute>>>();
        unsafe {
            base.write_bytes(0, count);
            core::slice::from_raw_parts_mut(base, count)
        }
    };
    let at = |offset| input.cast::<u8>().wrapping_add(offset).cast::<Attribute>();
    // len is the first repr(C) field. The final diagnostic only needs a u16.
    let length_at = |offset| unsafe { at(offset).cast::<u16>().read() };
    let (end, remaining) = rtattr::collect(len, flags, slots, length_at, |offset| {
        let header = at(offset);
        // collect validated the length field before requesting the type.
        unsafe { ((*header).kind, NonNull::new_unchecked(header)) }
    });
    if remaining != 0 {
        let length = length_at(end);
        unsafe {
            fprintf(
                stderr,
                c"!!!Deficit %d, rta_len=%d\n".as_ptr(),
                remaining,
                c_int::from(length),
            );
        }
    }
    0
}
