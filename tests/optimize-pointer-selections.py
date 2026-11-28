#!/usr/bin/env python3
"""Exercise competing and dependent compiler source receipts on the same archive."""
# SPDX-License-Identifier: 0BSD
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from optimize_pointer_selections import ORDER, best_chain, optimize


class Chains(unittest.TestCase):
    key = "engine.a"
    parent = {"source_library_sha256": {key: "archive"}}

    def choice(self, n, older=None):
        return {"pilot": {"archive": self.key, "cargo_archive": self.key, "control_sha256": "archive",
                          "candidate_sha256": "archive", "raw_pointer_types_removed": n},
                "parent_receipts": older or {}}

    def test_later_independent_choice_beats_first(self):
        small, large = self.choice(3), self.choice(25)
        self.assertEqual(best_chain(self.parent, self.key, {ORDER[0]:[small], ORDER[2]:[large]}),
                         (25, {ORDER[2]:large}))

    def test_weaker_first_choice_unlocks_a_larger_total(self):
        small, large = self.choice(3), self.choice(10)
        later = self.choice(21, {ORDER[0]:small["pilot"]})
        self.assertEqual(best_chain(self.parent, self.key, {ORDER[0]:[large, small], ORDER[2]:[later]}),
                         (24, {ORDER[0]:small, ORDER[2]:later}))

    def test_unknown_parent_or_changed_dependency(self):
        self.assertEqual(best_chain(self.parent, "missing.a", {ORDER[0]:[self.choice(1)]}), (0, {}))
        wrong = self.choice(12, {ORDER[1]:self.choice(1)["pilot"]})
        self.assertEqual(best_chain(self.parent, self.key, {ORDER[2]:[wrong]}), (0, {}))

    def test_keep_existing_terminal_layout(self):
        parent = dict(self.parent, shared_ncurses_termtypes={self.key: "terminal"})
        self.assertEqual(best_chain(parent, self.key, {ORDER[0]:[self.choice(1)]}), (0, {}))

    def test_fixed_earlier_layers_are_dependencies(self):
        fixed = self.choice(9)["pilot"]
        parent = dict(self.parent, **{ORDER[1]: {self.key: fixed}})
        compatible = self.choice(7, {ORDER[1]: fixed})
        stale = self.choice(22)
        self.assertEqual(best_chain(parent, self.key, {ORDER[2]: [stale, compatible]}),
                         (7, {ORDER[2]: compatible}))
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            link, manifest = root / "link.json", root / "manifest.json"
            link.write_text(json.dumps(parent))
            manifest.write_text(json.dumps({self.key: compatible}))
            # Empty CLI option lists leave the corresponding earlier layers fixed.
            def recount(source, target, layers):
                self.assertEqual(json.loads(source.read_bytes()), parent)
                self.assertEqual([layer for layer, _ in layers], [ORDER[2]])
                self.assertEqual(json.loads(layers[0][1][0].read_bytes()), {self.key: compatible})
                target.mkdir()
                return dict(counts={"all": {"before": 31, "after": 24}}, binary_sha256="elf",
                            layers={ORDER[2]: {"deferred": {}}}, sources={})
            with patch("optimize_pointer_selections.compose", side_effect=recount):
                result = optimize(link, {ORDER[0]: [], ORDER[2]: [manifest]}, root / "compatible")
            self.assertEqual(result["raw_pointer_types_removed"], 7)
            for conflict in ORDER[:2]:
                with self.assertRaisesRegex(ValueError, "preceding"):
                    optimize(link, {conflict: [manifest]}, root / "trial")
            self.assertFalse((root / "trial").exists())

    def test_publish_only_after_recount_agrees(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            link, inputs, out = (root / name for name in ("parent.json", "inputs.json", "result"))
            link.write_text(json.dumps(self.parent))
            inputs.write_text(json.dumps({self.key: self.choice(12)}))
            layer = ORDER[1]
            def recount(parent, target, layers):
                target.mkdir()
                source, = layers[0][1]
                return dict(counts={"all":{"before":23,"after":11}}, binary_sha256="elf",
                            layers={layer:{"deferred":{}}}, sources={str(parent):"elf", str(source):"manifest"})
            with patch("optimize_pointer_selections.compose", side_effect=recount):
                proof = optimize(link, {layer:[inputs]}, out)
            saved = json.loads((out / "recount/results.json").read_bytes())
            self.assertTrue(all(Path(source).is_file() for source in saved["sources"]))
            self.assertEqual(proof["raw_pointer_types_removed"], 12)
            inputs.write_text(json.dumps({self.key:self.choice(11)}))
            rejected = root / "rejected"
            with patch("optimize_pointer_selections.compose", side_effect=recount), self.assertRaises(ValueError):
                optimize(link, {layer:[inputs]}, rejected)
            self.assertFalse(rejected.exists())

if __name__ == "__main__":
    unittest.main()
