#!/usr/bin/env python3
"""Check that shared-layout edits preserve nominal variants and unrelated compiler inputs."""
# SPDX-License-Identifier: 0BSD
from hashlib import sha256
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_leaf_layout_pilot import substitute
from check_e2fsprogs_dirhash_arrays import source_list_digest
from prepare_leaf_layouts import replay_layer
from refresh_leaf_layout_pilots import current_selection
from rank_leaf_c_layouts import leaf_layouts
from verify_c_string_sources import syntax_tool

DECL = b"""#[derive(Copy, Clone)]
#[repr(C)]
pub struct record {
    pub bytes: *const word,
}
"""
DATA = b"pub type word = u8;\n" + DECL


class LayoutSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scanner = syntax_tool("leaf-layouts")

    def test_refresh_requires_unique_compatible_layouts_in_the_archive(self):
        old = {"record": dict(fingerprint="hash", copies=2, pointer_fields=1)}
        row = dict(name="record", declaration_and_field_types_sha256="hash", pointer_fields=1, archives={"a":4})
        self.assertEqual(current_selection([row], "a", old), {"record":dict(old["record"], copies=4)})
        self.assertIsNone(current_selection([row], "b", old))
        self.assertIsNone(current_selection([row, row], "a", old))
        self.assertIsNone(current_selection([dict(row, declaration_and_field_types_sha256="other")], "a", old))

    def select(self, consumer=DATA, copies=2):
        with TemporaryDirectory() as root:
            crate = Path(root)
            inputs = {"lib.rs": b"pub mod a;\npub mod b;\npub mod c;\n", "a.rs": DATA, "b.rs": consumer,
                      "c.rs": DATA.replace(b"= u8;", b"= u16;")}
            sources = {}
            for name, data in inputs.items():
                (crate / name).write_bytes(data)
                sources[name] = sha256(data).hexdigest()
            name, fingerprint, fields = leaf_layouts(DATA)[0]
            return substitute(crate, sources, {name: dict(fingerprint=fingerprint, pointer_fields=fields, copies=copies)},
                              scanner=self.scanner)

    def test_alias_resolution_excludes_same_spelling_with_different_layout(self):
        changes, facts = self.select()
        self.assertEqual(set(changes), {"b.rs"})
        self.assertEqual(changes["b.rs"], DATA.replace(DECL, b"pub use crate::a::record;" + b"\n" * DECL.count(b"\n")))
        self.assertEqual(facts["raw_pointer_types_removed"], 1)

    def test_replay_binds_layout_owners_and_parent_bytes(self):
        data = {"lib.rs": b"pub mod a;\npub mod b;\npub mod c;\n", "a.rs": DATA, "b.rs": DATA,
                "c.rs": DATA.replace(b"= u8;", b"= u16;")}
        hashes = {p: sha256(v).hexdigest() for p, v in data.items()}
        changes, facts = self.select()
        result = {**hashes, **{p: sha256(v).hexdigest() for p,v in changes.items()}}
        row = dict(facts, compiler_selected_sources=len(data), parent_sources_sha256=source_list_digest(hashes),
                   candidate_sources_sha256=source_list_digest(result))
        self.assertEqual(replay_layer(hashes, data.__getitem__, row, self.scanner), changes)
        wrong_owner = {"record": dict(facts["leaf_layouts"]["record"], provider="c.rs")}
        with self.assertRaises(ValueError):
            replay_layer(hashes, data.__getitem__, dict(row, leaf_layouts=wrong_owner), self.scanner)
        data["a.rs"] += b"\n"
        with self.assertRaises(ValueError):
            replay_layer(hashes, data.__getitem__, row, self.scanner)

    def test_additional_representation_attribute(self):
        with self.assertRaisesRegex(ValueError, "additional attribute"):
            self.select(DATA.replace(DECL, b"#[repr(align(32))]\n" + DECL))

    def test_extra_attribute_hidden_by_comment(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.select(DATA.replace(DECL, b"#[repr(align(32))]\n// another attribute follows\n" + DECL))

    def test_alias_only_present_in_comment(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.select(b"/*\npub type word = u8;\n*/\n" + DECL)

    def test_receipt_rejects_missing_consumer(self):
        with self.assertRaisesRegex(ValueError, "linked declarations differ"):
            self.select(copies=3)


if __name__ == "__main__":
    unittest.main()
