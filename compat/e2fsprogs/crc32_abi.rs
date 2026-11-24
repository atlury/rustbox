// SPDX-License-Identifier: GPL-2.0-only
#![no_std]
#![deny(unsafe_op_in_unsafe_fn)]
mod crc32;

/// For a nonempty input the caller owns one allocation with `len` initialized
/// bytes, readable during this call. Zero-length calls may pass null.
unsafe fn checksum<const REFLECTED: bool>(seed: u32, data: *const u8, len: usize) -> u32 {
    if len == 0 {
        return seed;
    }
    // SAFETY: The two upstream entrypoints require this readable byte region.
    crc32::checksum::<REFLECTED>(seed, unsafe { core::slice::from_raw_parts(data, len) })
}

#[cfg_attr(rustbox_multicall, export_name = "rustbox_e2fsprogs_crc32c_le")]
#[cfg_attr(not(rustbox_multicall), no_mangle)]
pub unsafe extern "C" fn ext2fs_crc32c_le(seed: u32, data: *const u8, len: usize) -> u32 {
    unsafe { checksum::<true>(seed, data, len) }
}

#[cfg_attr(rustbox_multicall, export_name = "rustbox_e2fsprogs_crc32_be")]
#[cfg_attr(not(rustbox_multicall), no_mangle)]
pub unsafe extern "C" fn ext2fs_crc32_be(seed: u32, data: *const u8, len: usize) -> u32 {
    unsafe { checksum::<false>(seed, data, len) }
}
