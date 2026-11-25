// SPDX-License-Identifier: GPL-2.0-only
// Test-only adapter. The caller supplies the canonical table and the exact input bound.
#[no_mangle]
pub unsafe extern "C" fn trie_offset(
    table: *const u8, size: usize, root: usize, input: *const u8, length: usize,
) -> isize {
    let table = core::slice::from_raw_parts(table, size);
    let leaf = utf8_trie::lookup(table, root, |i| {
        if i < length { Some(*input.add(i)) } else { None }
    });
    match leaf {
        None => -1,
        Some(utf8_trie::Leaf::Hangul(start)) => -2 - start as isize,
        Some(utf8_trie::Leaf::Table(first)) => (first as *const u8).offset_from(table.as_ptr()),
    }
}
