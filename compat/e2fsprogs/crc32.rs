// SPDX-License-Identifier: GPL-2.0-only
#![forbid(unsafe_code)]

// E2fsprogs uses reflected Castagnoli CRC32C and big-endian Ethernet CRC32.
// The caller supplies the initial CRC and receives it without a final XOR.
const fn tables<const REFLECTED: bool>() -> [[u32; 256]; 8] {
    let mut rows = [[0; 256]; 8];
    let mut index = 0;
    while index < 256 {
        let mut value = if REFLECTED { index as u32 } else { (index as u32) << 24 };
        let mut bit = 0;
        while bit < 8 {
            value = if REFLECTED {
                (value >> 1) ^ if value & 1 != 0 { 0x82f63b78 } else { 0 }
            } else {
                (value << 1) ^ if value >> 31 != 0 { 0x04c11db7 } else { 0 }
            };
            bit += 1;
        }
        rows[0][index] = value;
        index += 1;
    }
    let mut row = 1;
    while row < 8 {
        let mut i = 0;
        while i < 256 {
            let prev = rows[row - 1][i];
            rows[row][i] = if REFLECTED {
                (prev >> 8) ^ rows[0][(prev & 255) as usize]
            } else {
                (prev << 8) ^ rows[0][(prev >> 24) as usize]
            };
            i += 1;
        }
        row += 1;
    }
    rows
}

static CASTAGNOLI: [[u32; 256]; 8] = tables::<true>();
static ETHERNET: [[u32; 256]; 8] = tables::<false>();

pub fn checksum<const REFLECTED: bool>(mut crc: u32, data: &[u8]) -> u32 {
    let table = if REFLECTED { &CASTAGNOLI } else { &ETHERNET };
    let mut chunks = data.chunks_exact(8);
    for block in &mut chunks {
        let seed = if REFLECTED { crc.to_le_bytes() } else { crc.to_be_bytes() };
        crc = table[7][usize::from(block[0] ^ seed[0])]
            ^ table[6][usize::from(block[1] ^ seed[1])]
            ^ table[5][usize::from(block[2] ^ seed[2])]
            ^ table[4][usize::from(block[3] ^ seed[3])]
            ^ table[3][usize::from(block[4])]
            ^ table[2][usize::from(block[5])]
            ^ table[1][usize::from(block[6])]
            ^ table[0][usize::from(block[7])];
    }
    for &byte in chunks.remainder() {
        crc = if REFLECTED {
            (crc >> 8) ^ table[0][usize::from(crc as u8 ^ byte)]
        } else {
            (crc << 8) ^ table[0][usize::from((crc >> 24) as u8 ^ byte)]
        };
    }
    crc
}
