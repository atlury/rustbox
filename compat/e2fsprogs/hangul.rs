// SPDX-License-Identifier: GPL-2.0-only
// Algorithmic Hangul decomposition from E2fsprogs lib/ext2fs/nls_utf8.c.
#[forbid(unsafe_code)]
mod hangul_leaf {
    pub(super) enum Leaf {
        Lv([u8; 9]),
        Lvt([u8; 12]),
    }

    fn encode3(value: u32) -> [u8; 3] {
        [(0xe0 | (value >> 12)) as u8, (0x80 | ((value >> 6) & 63)) as u8,
         (0x80 | (value & 63)) as u8]
    }

    pub(super) fn decompose([a, b, c]: [u8; 3]) -> Leaf {
        let scalar = (u32::from(a & 15) << 12) | (u32::from(b & 63) << 6) | u32::from(c & 63);
        let index = scalar.wrapping_sub(0xac00);
        let [l0, l1, l2] = encode3(0x1100 + index / 588);
        let [v0, v1, v2] = encode3(0x1161 + index % 588 / 28);
        let trailing = index % 28;
        if trailing == 0 {
            Leaf::Lv([2, 255, l0, l1, l2, v0, v1, v2, 0])
        } else {
            let [t0, t1, t2] = encode3(0x11a7 + trailing);
            Leaf::Lvt([2, 255, l0, l1, l2, v0, v1, v2, t0, t1, t2, 0])
        }
    }
}
