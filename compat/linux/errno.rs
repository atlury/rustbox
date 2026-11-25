// SPDX-License-Identifier: 0BSD
pub(crate) mod rustbox_errno {
    use core::ffi::c_int;

    extern "C" {
        fn __errno_location() -> *mut c_int;
    }

    #[inline(always)]
    pub(crate) fn get() -> c_int {
        // glibc supplies the current thread's live, aligned errno cell.
        unsafe { __errno_location().read() }
    }

    #[inline(always)]
    pub(crate) fn set(value: c_int) {
        // Obtain the cell at the point of the store. No reference or address escapes.
        unsafe { __errno_location().write(value) }
    }
}
