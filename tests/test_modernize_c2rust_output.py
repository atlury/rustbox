#!/usr/bin/env python3
"""Regression tests for the deliberately narrow C2Rust stable spelling pass."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "modernize_c2rust_output", ROOT / "scripts/modernize_c2rust_output.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class OpaqueUseTests(unittest.TestCase):
    def transform(self, body: str) -> str:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "generated.rs"
            path.write_text(body, encoding="utf-8")
            MODULE.transform_rust(path)
            return path.read_text(encoding="utf-8")

    def test_raw_pointer_types_are_accepted(self) -> None:
        output = self.transform(
            "pub type opaque;\nfn f(a: *const opaque, b: *mut opaque) {}\n"
        )
        self.assertIn("pub struct opaque", output)

    def test_typed_null_pointer_constructors_are_accepted(self) -> None:
        output = self.transform(
            "pub type opaque;\n"
            "fn f() { let _ = core::ptr::null::<opaque>(); "
            "let _ = core::ptr::null_mut::<opaque>(); }\n"
        )
        self.assertIn("pub struct opaque", output)

    def test_by_value_use_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "non-pointer use"):
            self.transform("pub type opaque;\nfn f(value: opaque) {}\n")

    def test_pointer_use_does_not_mask_by_value_use_on_same_line(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "non-pointer use"):
            self.transform(
                "pub type opaque;\nfn f(pointer: *mut opaque, value: opaque) {}\n"
            )

    def test_mutable_static_address_uses_raw_pointer_operator(self) -> None:
        output = self.transform(
            "pub static mut failure: i32 = 1;\n"
            "fn f() { let _ = &mut failure as *mut i32; }\n"
        )
        self.assertIn("&raw mut failure as *mut i32", output)

    def test_local_mutable_address_is_not_rewritten(self) -> None:
        output = self.transform(
            "fn f() { let mut value = 1; let _ = &mut value as *mut i32; }\n"
        )
        self.assertIn("&mut value as *mut i32", output)


if __name__ == "__main__":
    unittest.main()
