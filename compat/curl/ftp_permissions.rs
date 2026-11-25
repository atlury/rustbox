// SPDX-License-Identifier: curl
#[forbid(unsafe_code)]
fn ftp_pl_get_permission(text: [u8; 9]) -> u32 {
    const INVALID: u32 = 0x0100_0000;
    let mut mode = 0;
    for (class, field) in text.chunks_exact(3).enumerate() {
        let shift = 6 - 3 * class;
        mode |= match field[0] {
            b'r' => 4 << shift,
            b'-' => 0,
            _ => INVALID,
        };
        mode |= match field[1] {
            b'w' => 2 << shift,
            b'-' => 0,
            _ => INVALID,
        };
        let special = if class == 2 { b't' } else { b's' };
        mode |= match field[2] {
            b'x' => 1 << shift,
            b'-' => 0,
            c if c == special => (1 << shift) | (0o4000 >> class),
            c if c == special.to_ascii_uppercase() => 0o4000 >> class,
            _ => INVALID,
        };
    }
    mode
}
