// SPDX-License-Identifier: GPL-2.0-only
#![forbid(unsafe_code)]

// Reflected representation of the upstream CRC-16 polynomial 0x8005.
const fn table() -> [u16; 256] {
    let mut entries = [0; 256];
    let mut i = 0;
    while i < entries.len() {
        let mut value = i as u16;
        let mut bit = 0;
        while bit < 8 {
            let carry = value & 1;
            value >>= 1;
            if carry != 0 {
                value ^= 0xa001;
            }
            bit += 1;
        }
        entries[i] = value;
        i += 1;
    }
    entries
}

const TABLE: [u16; 256] = table();

pub fn checksum(mut seed: u32, bytes: &[u8]) -> u32 {
    for &byte in bytes {
        let index = (seed as u8) ^ byte;
        seed = u32::from(((seed as u16) >> 8) ^ TABLE[usize::from(index)]);
    }
    seed
}
