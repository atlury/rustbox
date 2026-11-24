// SPDX-License-Identifier: GPL-2.0-only
#![no_std]
#![deny(unsafe_op_in_unsafe_fn)]

mod crc16;

use core::ffi::{c_uint, c_void};

/// Compute the E2fsprogs group descriptor CRC.
///
/// # Safety
/// For nonzero length the caller must supply `len` initialized bytes in one
/// live allocation, readable without mutation for the duration of this call.
/// The x86_64 Linux ABI guarantees every unsigned-int length fits in isize.
#[cfg_attr(rustbox_multicall, export_name = "rustbox_e2fsprogs_crc16")]
#[cfg_attr(not(rustbox_multicall), no_mangle)]
pub unsafe extern "C" fn ext2fs_crc16(seed: c_uint, buffer: *const c_void, len: c_uint) -> c_uint {
    if len == 0 {
        return seed;
    }
    // SAFETY: The C caller supplies the readable region described above.
    let bytes = unsafe { core::slice::from_raw_parts(buffer.cast::<u8>(), len as usize) };
    crc16::checksum(seed, bytes)
}
