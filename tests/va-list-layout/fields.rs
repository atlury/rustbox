// SPDX-License-Identifier: 0BSD
#[no_mangle]
pub extern "C" fn rust_layout(field: u32) -> usize {
    use core::mem::{align_of, offset_of, size_of};
    match field {
        0 => size_of::<__va_list_tag>(),
        1 => align_of::<__va_list_tag>(),
        2 => offset_of!(__va_list_tag, gp_offset),
        3 => offset_of!(__va_list_tag, fp_offset),
        4 => offset_of!(__va_list_tag, overflow_arg_area),
        5 => offset_of!(__va_list_tag, reg_save_area),
        _ => usize::MAX,
    }
}

#[no_mangle]
pub extern "C" fn rust_field(tag: &__va_list_tag, field: u32) -> usize {
    match field {
        0 => tag.gp_offset as usize,
        1 => tag.fp_offset as usize,
        2 => tag.overflow_arg_area as usize,
        3 => tag.reg_save_area as usize,
        _ => usize::MAX,
    }
}
