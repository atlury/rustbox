// SPDX-License-Identifier: 0BSD
use std::ffi::CStr;

const EMPTY: *const ::core::ffi::c_char = b"\0" as *const u8 as *const ::core::ffi::c_char;
macro_rules! spelling { ($($item:tt)*) => { stringify!($($item)*) }; }
fn main() {
    let escaped = b"line\n\t\\\"\xff\0"
        as *const u8
        as *const ::core::ffi::c_char;
    let inside = b"a\0b\0" as *const u8 as *const ::core::ffi::c_char;
    let missing = b"nonul" as *const u8 as *const ::core::ffi::c_char;
    let other = b"other\0" as *const u8 as *const i8;
    let token = spelling!(b"macro\0" as *const u8 as *const ::core::ffi::c_char);
    let comment = r#"b"argument\0" as *const u8 as *const ::core::ffi::c_char"#;
    assert_eq!(unsafe { CStr::from_ptr(EMPTY) }.to_bytes_with_nul(), b"\0");
    assert_eq!(unsafe { CStr::from_ptr(escaped) }.to_bytes_with_nul(), b"line\n\t\\\"\xff\0");
    assert_eq!(unsafe { CStr::from_ptr(inside) }.to_bytes(), b"a");
    assert_eq!(unsafe { *missing }, 110);
    assert_eq!(unsafe { *other }, 111);
    assert!(token.contains("macro") && comment.contains("argument"));
    println!("{token}\n{comment}");
}
