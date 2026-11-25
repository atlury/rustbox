// SPDX-License-Identifier: curl
#[forbid(unsafe_code)]
fn checkmonth(word: [u8; 3]) -> ::core::ffi::c_int {
    match &word.map(|byte| byte.to_ascii_lowercase()) {
        b"jan" => 0,
        b"feb" => 1,
        b"mar" => 2,
        b"apr" => 3,
        b"may" => 4,
        b"jun" => 5,
        b"jul" => 6,
        b"aug" => 7,
        b"sep" => 8,
        b"oct" => 9,
        b"nov" => 10,
        b"dec" => 11,
        _ => -1,
    }
}
