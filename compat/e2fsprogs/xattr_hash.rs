// SPDX-License-Identifier: LGPL-2.0-only
// E2fsprogs lib/ext2fs/ext_attr.c, portable signed and unsigned name hashes.
mod xattr_hash {
    #![forbid(unsafe_code)]

    pub(super) fn compute<const SIGNED: bool>(name: &[u8], value: &[u32]) -> u32 {
        let mut hash = 0u32;
        for &byte in name {
            let extended = if SIGNED {
                i32::from(byte as i8) as u32
            } else {
                u32::from(byte)
            };
            hash = hash.rotate_left(5) ^ extended;
        }
        for &word in value {
            hash = hash.rotate_left(16) ^ u32::from_le(word);
        }
        hash
    }
}

// The caller supplies a header immediately followed by its name. Inline values
// include the padding up to a whole word. External values never access data.
unsafe fn hash_xattr_entry<const SIGNED: bool>(
    entry: *const ext2_ext_attr_entry,
    data: *const ::core::ffi::c_void,
) -> u32 {
    let name_len = unsafe { (*entry).e_name_len } as usize;
    let name = unsafe { ::core::slice::from_raw_parts(entry.add(1).cast::<u8>(), name_len) };
    let words = if unsafe { (*entry).e_value_inum } == 0 {
        // The canonical size expression uses 32-bit unsigned arithmetic.
        unsafe { (*entry).e_value_size }.wrapping_add(3) >> 2
    } else {
        0
    };
    let value = if words == 0 {
        &[]
    } else {
        unsafe { ::core::slice::from_raw_parts(data.cast::<u32>(), words as usize) }
    };
    xattr_hash::compute::<SIGNED>(name, value)
}

#[no_mangle]
pub unsafe extern "C" fn ext2fs_ext_attr_hash_entry(
    entry: *mut ext2_ext_attr_entry,
    data: *mut ::core::ffi::c_void,
) -> u32 {
    unsafe { hash_xattr_entry::<false>(entry, data) }
}

#[no_mangle]
pub unsafe extern "C" fn ext2fs_ext_attr_hash_entry_signed(
    entry: *mut ext2_ext_attr_entry,
    data: *mut ::core::ffi::c_void,
) -> u32 {
    unsafe { hash_xattr_entry::<true>(entry, data) }
}
