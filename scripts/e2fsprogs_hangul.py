"""Substitute the three private generated Hangul helpers at their sole trie lookup caller."""
# SPDX-License-Identifier: GPL-2.0-only
import hashlib
from pathlib import Path
import re

RUST = Path(__file__).resolve().parents[1] / "compat/e2fsprogs/hangul.rs"
SHA = (
    "99162e0fa63c9c0bdd26f2821a4f3cce2491433de2a4fb29baf10ba528e29524",
    "32ec015f60b6f96d3df73608641fc44f37c6239daf03a3a948a197737ae655f8",
    "d281e19e9aafe6be150f01581f8d64141f3d1b4c0259f42680a1deb19ec66ba5",
    "4e2aaef4783c2c657a2d250f56035904a296b30624b745db73b6bafa418e10b0",
    "7f6e648c20b0cf51e62937f08c3a42689baeb8b9c76a94ae3a1731fee4a9cd77",
    "d75370f9e5251f014874392b1151088b572a21328320559d3147cfee3d600e6e",
)
OLD_CALL = b"""        trie = utf8hangul(s.offset(-(2 as ::core::ffi::c_int as isize)), hangul)
            as *const utf8trie_t;"""
NEW_CALL = b"""        // This trie marker identifies a three-byte syllable. The lookup has
        // consumed two bytes. Copy the input before writing to cursor storage.
        let input = s.sub(2).cast::<[u8; 3]>().read();
        match hangul_leaf::decompose(input) {
            hangul_leaf::Leaf::Lv(bytes) => hangul.cast::<[u8; 9]>().write(bytes),
            hangul_leaf::Leaf::Lvt(bytes) => hangul.cast::<[u8; 12]>().write(bytes),
        }
        trie = hangul;"""


def replace_hangul(module):
    data = module.read_bytes()
    decode, constants, decompose, lookup, following = [data.index(fragment) for fragment in (
        b'unsafe extern "C" fn utf8decode3(', b'pub const BITNUM:', b'unsafe extern "C" fn utf8hangul(',
        b'unsafe extern "C" fn utf8nlookup(', b'unsafe extern "C" fn utf8lookup(')]
    parts = data[decode:constants], data[decompose:lookup], data[lookup:following]
    owners = (data[constants:decompose], data[following:data.index(b'unsafe extern "C" fn utf8_casefold(')],
              data[data.index(b'unsafe extern "C" fn utf8_validate('):data.index(b'unsafe extern "C" fn utf8_casefold_cmp(')])
    if (tuple(hashlib.sha256(part).hexdigest() for part in (*parts, *owners)) != SHA
            or data.count(b"pub hangul: [::core::ffi::c_uchar; 12],") != 1):
        raise ValueError("Hangul helpers or trie caller differ from the reviewed source")
    names = (b"utf8decode3", b"utf8encode3", b"utf8hangul")
    if [len(re.findall(rb"\b" + name + rb"\b", data)) for name in names] != [2, 4, 2] or parts[2].count(OLD_CALL) != 1:
        raise ValueError("unexpected Hangul call graph")
    result = data[:decode] + RUST.read_bytes() + data[constants:decompose] + parts[2].replace(OLD_CALL, NEW_CALL) + data[following:]
    module.write_bytes(result)
    pointer = rb"\*(?:mut|const)\b"
    return {"module_before": hashlib.sha256(data).hexdigest(), "module_after": hashlib.sha256(result).hexdigest(),
            "raw_pointer_type_tokens_removed": len(re.findall(pointer, data)) - len(re.findall(pointer, result))}
