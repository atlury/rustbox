#!/usr/bin/env python3
"""Tests for deterministic C2Rust Cargo-scaffold preparation."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "prepare_c2rust_scaffold", ROOT / "scripts/prepare_c2rust_scaffold.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ManifestTests(unittest.TestCase):
    def test_dependency_is_inserted_in_sorted_order(self) -> None:
        manifest = "[package]\nname = \"x\"\n[dependencies]\nf128 = \"0.2\"\nlibc = \"0.2\"\n"
        actual = MODULE.add_dependency(manifest, "num-traits", "0.2")
        self.assertIn(
            '[dependencies]\nf128 = "0.2"\nlibc = "0.2"\nnum-traits = "0.2"\n',
            actual,
        )

    def test_existing_dependency_is_unchanged(self) -> None:
        manifest = "[dependencies]\nnum-traits = \"0.2\"\n"
        self.assertEqual(
            MODULE.add_dependency(manifest, "num-traits", "0.2"), manifest
        )

    def test_missing_dependencies_section_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "no \\[dependencies\\]"):
            MODULE.add_dependency("[package]\nname = \"x\"\n", "num-traits", "0.2")


if __name__ == "__main__":
    unittest.main()
