// SPDX-License-Identifier: LGPL-2.0-only
// E2fsprogs lib/ext2fs/bitops.c. Each ABI entry accesses only the designated byte.
mod bitmap_byte {
    #![forbid(unsafe_code)]

    pub(super) fn position(nr: u64) -> (usize, u8) {
        ((nr >> 3) as usize, 1u8 << (nr & 7))
    }

    pub(super) fn update(byte: &mut u8, mask: u8, set: bool) -> i32 {
        let old = *byte & mask;
        *byte = if set { *byte | mask } else { *byte & !mask };
        i32::from(old)
    }
}

/// The caller must provide a writable bitmap containing bit `nr`.
#[no_mangle]
pub unsafe extern "C" fn ext2fs_set_bit64(nr: u64, addr: *mut ::core::ffi::c_void) -> i32 {
    let (offset, mask) = bitmap_byte::position(nr);
    let byte = unsafe { &mut *addr.cast::<u8>().add(offset) };
    bitmap_byte::update(byte, mask, true)
}

/// The caller must provide a writable bitmap containing bit `nr`.
#[no_mangle]
pub unsafe extern "C" fn ext2fs_clear_bit64(nr: u64, addr: *mut ::core::ffi::c_void) -> i32 {
    let (offset, mask) = bitmap_byte::position(nr);
    let byte = unsafe { &mut *addr.cast::<u8>().add(offset) };
    bitmap_byte::update(byte, mask, false)
}

/// The caller must provide a readable bitmap containing bit `nr`.
#[no_mangle]
pub unsafe extern "C" fn ext2fs_test_bit64(nr: u64, addr: *const ::core::ffi::c_void) -> i32 {
    let (offset, mask) = bitmap_byte::position(nr);
    i32::from(unsafe { *addr.cast::<u8>().add(offset) } & mask)
}

#[no_mangle]
pub unsafe extern "C" fn ext2fs_set_bit(nr: u32, addr: *mut ::core::ffi::c_void) -> i32 {
    unsafe { ext2fs_set_bit64(u64::from(nr), addr) }
}

#[no_mangle]
pub unsafe extern "C" fn ext2fs_clear_bit(nr: u32, addr: *mut ::core::ffi::c_void) -> i32 {
    unsafe { ext2fs_clear_bit64(u64::from(nr), addr) }
}

#[no_mangle]
pub unsafe extern "C" fn ext2fs_test_bit(nr: u32, addr: *const ::core::ffi::c_void) -> i32 {
    unsafe { ext2fs_test_bit64(u64::from(nr), addr) }
}
