// SPDX-License-Identifier: GPL-2.0-or-later
#![forbid(unsafe_code)]

/// IPRoute2 7.3.0 wire limit for rtnl_from_file and rtnl_listen.
pub const WIRE_LIMIT: usize = 16_384;

/// Bytes through the u16 diagnostic at the next four-byte record boundary.
pub const fn diagnostic_tail(bytes: usize) -> usize {
    let padding = (4 - bytes % 4) % 4;
    padding + core::mem::size_of::<u16>()
}

// Keep the suffix inside the same initialized array as the message. C callers
// receive a pointer derived from the whole array and cast it to Linux headers.
#[repr(align(8))]
pub struct MonitorBuffer([u8; WIRE_LIMIT + diagnostic_tail(WIRE_LIMIT)]);

impl MonitorBuffer {
    pub fn new() -> Self {
        Self([0; WIRE_LIMIT + diagnostic_tail(WIRE_LIMIT)])
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

    // x86_64 Linux: NLMSG_HDRLEN + NLMSG_ALIGN(sizeof(struct ndmsg)).
    const ATTR_START: usize = 28;

    #[test]
    fn heap_suffix_fits_when_receive_is_shorter_than_capacity() {
        // rtnl_recvmsg uses a signed-int size and a 32768-byte minimum.
        for capacity in [32768, 32769, 32770, 32771, 65536, i32::MAX as usize] {
            let allocated = capacity + diagnostic_tail(capacity);
            for used in (0..32768).chain(capacity - 7..=capacity) {
                let initialized = used + diagnostic_tail(used);
                assert!(initialized <= allocated);
                assert_eq!(initialized, used.next_multiple_of(4) + 2);
            }
        }
    }

    #[test]
    fn top_level_fdb_cursor_fits_for_every_accepted_wire_length() {
        let mut buf = MonitorBuffer::new();
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

    #[test]
    fn final_message_fits_at_each_aligned_live_record_start() {
        let buf = MonitorBuffer::new();
        for start in (0..=WIRE_LIMIT - ATTR_START).step_by(4) {
            let payload_start = start + ATTR_START;
            // For each residue modulo four, exercise the largest record that
            // fits here. Shorter records of that residue end earlier.
            for unused in 0..=3.min(WIRE_LIMIT - payload_start) {
                let len = WIRE_LIMIT - payload_start - unused;
                let (offset, _) =
                    rtattr::collect(len as i32, 0, &mut [], |_| len as u16, |_| (0, ()));
                let cursor = payload_start + offset;
                assert!(cursor <= WIRE_LIMIT);
                assert!(buf.0.get(cursor..cursor + 2).is_some());
            }
        }
    }
}
