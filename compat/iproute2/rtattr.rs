// SPDX-License-Identifier: GPL-2.0-or-later
#![forbid(unsafe_code)]

/// Scan four-byte Linux rtattr headers. The caller supplies empty slots and
/// access to initialized header fields. Payload and alignment bytes are opaque.
/// Return the cursor and signed remaining length used by the C diagnostic.
pub fn collect<T>(
    mut remaining: i32,
    flags: u16,
    slots: &mut [Option<T>],
    length_at: impl Fn(usize) -> u16,
    entry_at: impl Fn(usize) -> (u16, T),
) -> (usize, i32) {
    let mut offset = 0;
    while remaining >= 4 {
        let length = i32::from(length_at(offset));
        if length < 4 || length > remaining {
            break;
        }
        let (kind, location) = entry_at(offset);
        if let Some(slot) = slots.get_mut(usize::from(kind & !flags)) {
            if slot.is_none() {
                *slot = Some(location);
            }
        }
        let stride = (length + 3) & !3;
        offset += stride as usize;
        remaining -= stride;
    }
    (offset, remaining)
}
