// SPDX-License-Identifier: GPL-2.0-only
#![no_std]
#![deny(unsafe_op_in_unsafe_fn)]

use core::ffi::{c_uint, c_void};

fn bitcount(bytes: &[u8]) -> u32 {
    let (words, tail) = bytes.as_chunks::<8>();
    let count = words.iter().fold(0u32, |count, word| {
        count.wrapping_add(u64::from_ne_bytes(*word).count_ones())
    });
    tail.iter().fold(count, |count, byte| count.wrapping_add(byte.count_ones()))
}

/// Count set bits modulo 2^32, as in E2fsprogs' unsigned accumulator.
///
/// # Safety
/// For nonzero length, the caller supplies that many initialized bytes in one
/// allocation, readable without mutation during the call. The target is Linux
/// x86-64, where a c_uint length fits in isize.
#[no_mangle]
pub unsafe extern "C" fn rustbox_e2fsprogs_bitcount(buffer: *const c_void, len: c_uint) -> c_uint {
    if len == 0 {
        return 0;
    }
    // SAFETY: The C caller supplies the readable region described above.
    bitcount(unsafe { core::slice::from_raw_parts(buffer.cast::<u8>(), len as usize) })
}
