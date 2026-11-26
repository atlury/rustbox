// SPDX-License-Identifier: GPL-2.0-or-later
const RUSTBOX_CLEAR_COLOR: [u8; 8] = *b"\x1b[0m\0\0\0\0";

// iproute2 orders the attributes as interface, MAC, IPv4, IPv6, up, down, none.
// Every row ends in NUL, including the longest bold color escape.
fn rustbox_color_escape(dark: bool, attr: usize) -> &'static [u8; 8] {
    static LIGHT: [[u8; 8]; 7] = [
        *b"\x1b[36m\0\0\0",
        *b"\x1b[33m\0\0\0",
        *b"\x1b[35m\0\0\0",
        *b"\x1b[34m\0\0\0",
        *b"\x1b[32m\0\0\0",
        *b"\x1b[31m\0\0\0",
        RUSTBOX_CLEAR_COLOR,
    ];
    static DARK: [[u8; 8]; 7] = [
        *b"\x1b[1;36m\0",
        *b"\x1b[1;33m\0",
        *b"\x1b[1;35m\0",
        *b"\x1b[1;94m\0",
        *b"\x1b[1;32m\0",
        *b"\x1b[1;31m\0",
        RUSTBOX_CLEAR_COLOR,
    ];
    if dark {
        &DARK[attr]
    } else {
        &LIGHT[attr]
    }
}
