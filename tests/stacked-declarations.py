#!/usr/bin/env python3
"""Exercise the byte-level composition of two independently pinned declaration removals."""
# SPDX-License-Identifier: GPL-3.0-or-later
from hashlib import sha256
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_stacked_declarations as stacked
from inline_source_layout import WHITESPACE


class StackedDeclarations(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.crate = Path(scratch.name)
        definition = b"type Unused = *const i32;"
        declaration = b"fn unused(arg: *mut i32);"
        self.original = definition + b'\nextern "C" { ' + declaration + b" }\npub fn keep() -> i32 { 7 }\n"
        (self.crate / "lib.rs").write_bytes(self.original)
        self.sources = {"lib.rs": sha256(self.original).hexdigest()}
        start = self.original.index(declaration)
        self.span = [start, start + len(declaration)]
        self.erased = self.original.replace(declaration, declaration.translate(WHITESPACE))
        self.type_only = self.original.replace(definition, definition.translate(WHITESPACE))
        self.expected = self.type_only.replace(declaration, declaration.translate(WHITESPACE))

    def run_pair(self, type_only, stale=False):
        def receipt(data):
            return dict(archive="test.a", control_sha256="control", candidate_sha256="control",
                        raw_pointer_types_removed=1, parent_sources_sha256=stacked.source_list_digest(self.sources),
                        candidate_sources_sha256=stacked.source_digest(self.sources, {"lib.rs": data}))
        types, foreign = receipt(type_only), receipt(self.erased)
        types["candidate_sha256"] = "changed"
        foreign["ranges"] = {"lib.rs": [self.span]}
        if stale:
            types["candidate_sources_sha256"] = "different"
        with patch.object(stacked, "unused_types", return_value=({"lib.rs": type_only}, {})), \
             patch.object(stacked, "apply_spans", return_value=({"lib.rs": self.erased}, {})):
            return stacked.transform(self.crate, self.sources, types, foreign)

    def test_two_removals_in_one_module(self):
        changes, facts = self.run_pair(self.type_only)
        self.assertEqual(changes, {"lib.rs": self.expected})
        self.assertEqual(facts["raw_pointer_types_removed"], 2)

    def test_double_counted_range(self):
        with self.assertRaisesRegex(ValueError, "overlapping removals"):
            self.run_pair(self.erased)

    def test_changed_scanner_output(self):
        with self.assertRaisesRegex(ValueError, "source reconstruction"):
            self.run_pair(self.type_only, stale=True)


if __name__ == "__main__":
    unittest.main()
