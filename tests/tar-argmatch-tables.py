#!/usr/bin/env python3
"""Check that the tar table rewrite rejects storage escaping its one synchronous matcher call."""
# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_tar_argmatch_tables import replace

SOURCE = b'''static mut names: [*const ::core::ffi::c_char; 2] = [
    b"first\\0" as *const u8 as *const ::core::ffi::c_char,
    ::core::ptr::null::<::core::ffi::c_char>(),
];
fn parse() {
    __xargmatch_internal(context, arg,
        &raw const names as *const *const ::core::ffi::c_char, values, size, die, true);
}
'''


class Tables(unittest.TestCase):
    def test_preserves_argument_and_table_order(self):
        result = replace(SOURCE, "names", [b"first"])
        self.assertIn(b'Some(c"first"),\n    None,', result)
        self.assertIn(b'__xargmatch_internal(context, arg,', result)
        self.assertNotIn(b'static mut names', result)

    def test_refuses_other_users_or_changed_abi(self):
        for source in (SOURCE + b'fn capture() { keep(&raw const names); }',
                       SOURCE.replace(b'__xargmatch_internal', b'hold_for_later'),
                       SOURCE.replace(b'null::<', b'other::<')):
            with self.subTest(source=source), self.assertRaises(ValueError):
                replace(source, "names", [b"first"])

    def test_refuses_a_different_configuration(self):
        with self.assertRaises(ValueError):
            replace(SOURCE, "names", [b"first", b"extra"])


if __name__ == "__main__":
    unittest.main()
