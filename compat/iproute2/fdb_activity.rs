// SPDX-License-Identifier: GPL-2.0-or-later
#![forbid(unsafe_code)]

use crate::rtattr;

/// Parse the child stream of NDA_FDB_EXT_ATTRS. The receive owner supplies
/// initialized bytes through the aligned end and the u16 diagnostic field.
/// IPRoute2 prints flags from the first NFEA_ACTIVITY_NOTIFY child only.
pub fn decode(bytes: &[u8], payload_len: u16) -> (u8, Option<(i32, u16)>) {
    let field = |offset: usize| u16::from_ne_bytes([bytes[offset], bytes[offset + 1]]);
    let mut offsets = [None; 2];
    let (end, remaining) = rtattr::collect(
        i32::from(payload_len),
        0x8000, // NLA_F_NESTED
        &mut offsets,
        field,
        |offset| (field(offset + 2), offset + 4),
    );
    let diagnostic = (remaining != 0).then(|| (remaining, field(end)));
    (offsets[1].map_or(0, |offset| bytes[offset]), diagnostic)
}
