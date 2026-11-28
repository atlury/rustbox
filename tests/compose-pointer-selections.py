#!/usr/bin/env python3
"""Check that composing source selections preserves completed stages and omits deferred archives."""
# SPDX-License-Identifier: 0BSD
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from compose_pointer_selections import compose


class Composition(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.link = self.root / "release.json"
        self.base = dict(binary=dict(sha256="elf"), source_library_sha256={})
        self.link.write_text(json.dumps(self.base))
        self.old = self.root / "old.json"
        self.old.write_text(json.dumps({"missing.a": {"pilot": dict(archive="missing.a", control_sha256="a", candidate_sha256="a")}}))
        self.out = self.root / "out"

    def test_fully_deferred_stage(self):
        counts = {"raw_pointer_type_tokens": 201}
        with patch("rebase_va_list_layouts.measure", return_value={"all":counts,"counting_identical_files_once":counts}):
            result = compose(self.link, self.out, [("closed_inline_groups", [self.old])])
        self.assertEqual(result["counts"]["all"], {"before":201, "after":201})
        self.assertEqual(result["layers"]["closed_inline_groups"]["selected"], 0)
        self.assertIn("missing.a", result["layers"]["closed_inline_groups"]["deferred"])
        self.assertEqual(json.loads((self.out / "closed_inline_groups-link.json").read_bytes()), self.base)

    def test_rejects_ambiguous_or_reversed_layers(self):
        for layers in ([], ["shared_scalar_ffi","closed_inline_groups"], ["shared_scalar_ffi"] * 2):
            with self.assertRaises(ValueError):
                compose(self.link, self.out, [(k,[self.old]) for k in layers])
            self.assertFalse(self.out.exists())

    def test_preserves_existing_selection(self):
        self.base["shared_scalar_ffi"] = {"present":"archive"}
        self.link.write_text(json.dumps(self.base))
        with self.assertRaises(ValueError):
            compose(self.link, self.out, [("closed_inline_groups", [self.old])])
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
