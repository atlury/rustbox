// SPDX-License-Identifier: BSD-2-Clause OR GPL-3.0-or-later
#[forbid(unsafe_code)]
mod messages {
    use super::{MESSAGE_BYTES, MESSAGE_OFFSETS, SYMBOL_BYTES, SYMBOL_OFFSETS};
    use core::ffi::{c_char, CStr};
    use core::sync::atomic::{AtomicPtr, Ordering};

    pub const COUNT: usize = MESSAGE_OFFSETS.len() - 1;
    // Less owns overrides allocated by saven(), including old strings returned
    // before a reload. Preserve those C addresses and their allocation extent.
    static OVERRIDES: [AtomicPtr<c_char>; COUNT] =
        [const { AtomicPtr::new(core::ptr::null_mut()) }; COUNT];

    pub fn id(symbol: &CStr) -> u32 {
        SYMBOL_OFFSETS
            .windows(2)
            .position(|p| &SYMBOL_BYTES[usize::from(p[0])..usize::from(p[1])] == symbol.to_bytes())
            .map_or(0, |index| index as u32 + 1)
    }

    pub fn set(id: u32, value: *mut c_char) {
        OVERRIDES[id as usize - 1].store(value, Ordering::Release);
    }

    pub fn get(id: u32) -> *const c_char {
        let i = id as usize - 1;
        let override_ptr = OVERRIDES[i].load(Ordering::Acquire);
        if override_ptr.is_null() {
            let (start, end) = (MESSAGE_OFFSETS[i], MESSAGE_OFFSETS[i + 1]);
            MESSAGE_BYTES[usize::from(start)..usize::from(end)]
                .as_ptr()
                .cast()
        } else {
            override_ptr
        }
    }
}
