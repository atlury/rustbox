// SPDX-License-Identifier: GPL-2.0-or-later
#![forbid(unsafe_code)]

/// IPRoute2 7.3.0 rtnl_from_file's maximum on-disk message size.
pub const WIRE_LIMIT: usize = 16_384;

// Keep the suffix inside the same initialized array as the message. C callers
// receive a pointer derived from the whole array and cast it to Linux headers.
#[repr(align(8))]
pub struct ReplayBuffer([u8; WIRE_LIMIT + core::mem::size_of::<u16>()]);

impl ReplayBuffer {
    pub fn new() -> Self {
        Self([0; WIRE_LIMIT + core::mem::size_of::<u16>()])
    }

    pub fn as_mut_ptr(&mut self) -> *mut u8 {
        self.0.as_mut_ptr()
    }
}

#[cfg(test)]
#[path = "rtattr.rs"]
mod rtattr;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn top_level_fdb_cursor_fits_for_every_accepted_wire_length() {
        // x86_64 Linux: NLMSG_HDRLEN + NLMSG_ALIGN(sizeof(struct ndmsg)).
        const ATTR_START: usize = 28;
        let mut buf = ReplayBuffer::new();
        assert_eq!(buf.as_mut_ptr().align_offset(8), 0);
        for wire_len in ATTR_START..=WIRE_LIMIT {
            let len = wire_len - ATTR_START;
            // A single attribute of this size reaches the most distant cursor
            // possible: each previous accepted stride starts on a 4-byte boundary.
            let (end, remaining) =
                rtattr::collect(len as i32, 0, &mut [], |_| len as u16, |_| (0, ()));
            assert_eq!(remaining, len as i32 - end as i32);
            let aligned_end = (wire_len + 3) & !3;
            assert!(ATTR_START + end <= aligned_end);
            assert_eq!(buf.0.get(aligned_end..aligned_end + 2), Some(&[0, 0][..]));
        }
    }
}
