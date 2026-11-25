// SPDX-License-Identifier: GPL-2.0-only
// E2fsprogs lib/ext2fs/nls_utf8.c, compact trie lookup.
#[forbid(unsafe_code)]
mod utf8_trie {
    pub(super) enum Leaf<'a> {
        Table(&'a u8),
        Hangul(usize),
    }

    pub(super) fn lookup(
        table: &[u8],
        mut node: usize,
        mut byte_at: impl FnMut(usize) -> Option<u8>,
    ) -> Option<Leaf<'_>> {
        let mut input = 0;
        loop {
            let flags = *table.get(node)?;
            if flags & 0x08 != 0 {
                input += 1;
            }
            let right = byte_at(input)? & (1 << (flags & 7)) != 0;
            let width = usize::from((flags >> 4) & 3);
            let (distance, next_is_node) = if width == 0 {
                if right != (flags & 0x40 != 0) {
                    return None;
                }
                (1, flags & 0x80 != 0)
            } else if right {
                let bytes = table.get(node + 1..node + 1 + width)?;
                let distance = bytes.iter().rev().fold(0, |n, b| (n << 8) | usize::from(*b));
                if distance == 0 {
                    return None;
                }
                (distance, flags & 0x40 != 0)
            } else {
                (1 + width, flags & 0x80 != 0)
            };
            node = node.checked_add(distance)?;
            if !next_is_node {
                let leaf = table.get(node..)?;
                if *leaf.get(1)? == 255 && *leaf.get(2)? == 255 {
                    return input.checked_sub(2).map(Leaf::Hangul);
                }
                return Some(Leaf::Table(leaf.first()?));
            }
        }
    }
}
