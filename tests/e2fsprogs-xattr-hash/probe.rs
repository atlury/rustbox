// SPDX-License-Identifier: LGPL-2.0-only
#[repr(C)]
pub struct ext2_ext_attr_entry {
    pub e_name_len: u8,
    pub e_name_index: u8,
    pub e_value_offs: u16,
    pub e_value_inum: u32,
    pub e_value_size: u32,
    pub e_hash: u32,
}

include!("../../compat/e2fsprogs/xattr_hash.rs");
