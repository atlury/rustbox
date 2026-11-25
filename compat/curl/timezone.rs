// SPDX-License-Identifier: curl
#[forbid(unsafe_code)]
fn checktz(word: &[u8]) -> i32 {
    let minutes = match word {
        [b'J'] => return -1,
        [letter @ b'A'..=b'Z'] => tzone[usize::from(*letter - b'A')],
        b"NT" => 11 * 60,
        b"UT" => 0,
        [a, b, c] => return zone_offset(&tzthree, [*a, *b, *c, 0]),
        [a, b, c, d] => return zone_offset(&tzfoura, [*a, *b, *c, *d]),
        _ => return -1,
    };
    i32::from(minutes) * 60
}

#[forbid(unsafe_code)]
fn zone_offset(table: &[tzinfo], letters: [u8; 4]) -> i32 {
    let key = u32::from_be_bytes(letters);
    table.binary_search_by_key(&key, |entry| entry.tz)
        .map_or(-1, |index| i32::from(table[index].offset) * 60)
}
