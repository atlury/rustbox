// SPDX-License-Identifier: 0BSD
// GNU libc's ctype functions accept every unsigned byte in the active thread locale.
pub(crate) mod rustbox_ctype {
    use core::ffi::c_int;

    macro_rules! classification {
        ($name:ident, $symbol:ident, $bit:literal) => {
            #[inline]
            pub(crate) fn $name(byte: u8) -> c_int {
                unsafe extern "C" {
                    fn $symbol(c: c_int) -> c_int;
                }
                // The unsigned-byte domain is valid for every C locale.
                let classified = unsafe { $symbol(c_int::from(byte)) } != 0;
                // glibc stores its C classification bits in network byte order.
                // A compiler intrinsic may return any positive int for true.
                if classified { c_int::from(u16::from_be(1u16 << $bit)) } else { 0 }
            }
        };
    }

    classification!(upper, isupper, 0);
    classification!(lower, islower, 1);
    classification!(alpha, isalpha, 2);
    classification!(digit, isdigit, 3);
    classification!(xdigit, isxdigit, 4);
    classification!(space, isspace, 5);
    classification!(print, isprint, 6);
    classification!(graph, isgraph, 7);
    classification!(blank, isblank, 8);
    classification!(cntrl, iscntrl, 9);
    classification!(punct, ispunct, 10);
    classification!(alnum, isalnum, 11);
}
