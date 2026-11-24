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

    def test_multiline_typed_null_pointer_constructor_is_accepted(self) -> None:
        output = self.transform(
            "pub type opaque;\n"
            "static mut VALUE: *mut opaque = core::ptr::null::<\n"
            "    opaque,\n"
            ">() as *mut opaque;\n"
        )
        self.assertIn("pub struct opaque", output)

    def test_by_value_use_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "non-pointer use"):
            self.transform("pub type opaque;\nfn f(value: opaque) {}\n")

    def test_local_may_shadow_opaque_type_name(self) -> None:
        output = self.transform(
            "pub type opaque;\n"
            "pub type opaque_t = *mut opaque;\n"
            "fn consume(_: opaque_t) {}\n"
            "fn f() { let mut opaque: opaque_t = core::ptr::null_mut::<opaque>(); "
            "opaque = core::ptr::null_mut(); consume(opaque); }\n"
        )
        self.assertIn("pub struct opaque", output)

    def test_mutable_parameter_may_shadow_opaque_type_name(self) -> None:
        output = self.transform(
            "pub type dfa;\n"
            "fn f(mut dfa: bool, pointer: *mut dfa) { dfa = !dfa; consume(dfa, pointer); }\n"
        )
        self.assertIn("pub struct dfa", output)

    def test_shadowing_local_does_not_mask_by_value_type_use(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "non-pointer use"):
            self.transform(
                "pub type opaque;\n"
                "fn f() { let mut opaque: *mut opaque = core::ptr::null_mut(); }\n"
                "fn bad(value: opaque) {}\n"
            )

    def test_pointer_use_does_not_mask_by_value_use_on_same_line(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "non-pointer use"):
            self.transform(
                "pub type opaque;\nfn f(pointer: *mut opaque, value: opaque) {}\n"
            )

    def test_field_with_same_name_as_opaque_type_is_not_a_type_use(self) -> None:
        output = self.transform(
            "pub type tm_zone;\n"
            "struct tm { pub tm_zone: *const core::ffi::c_char }\n"
            "fn f(pointer: *mut tm_zone, value: *mut tm) { "
            "let _ = (*value).tm_zone; }\n"
        )
        self.assertIn("pub struct tm_zone", output)

    def test_pointer_only_alias_of_opaque_type_is_accepted(self) -> None:
        output = self.transform(
            "pub type __dirstream;\n"
            "pub type DIR = __dirstream;\n"
            "fn f(stream: *mut DIR) {}\n"
        )
        self.assertIn("pub struct __dirstream", output)

    def test_by_value_alias_of_opaque_type_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "non-pointer use"):
            self.transform(
                "pub type __dirstream;\n"
                "pub type DIR = __dirstream;\n"
                "fn f(stream: DIR) {}\n"
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

    def test_mutable_static_shared_address_uses_raw_pointer_operator(self) -> None:
        output = self.transform(
            "pub static mut count: i32 = 1;\n"
            "fn f() { let _ = &count as *const i32; }\n"
        )
        self.assertIn("&raw const count as *const i32", output)

    def test_stable_feature_attributes_are_removed(self) -> None:
        output = self.transform(
            "#![feature(c_variadic)]\n"
            "#![feature(extern_types)]\n"
            "#![feature(label_break_value)]\n"
            "#![feature(linkage)]\n"
            "#![feature(raw_ref_op)]\n"
            "#[linkage = \"external\"]\n"
            "pub fn exported() {}\n"
            "fn f() {}\n"
        )
        self.assertNotIn("#![feature(", output)
        self.assertNotIn("#[linkage", output)

    def test_obsolete_va_list_spelling_and_borrow_are_rewritten(self) -> None:
        output = self.transform(
            "unsafe fn f(mut args: ...) {\n"
            "    let mut copy: ::core::ffi::VaListImpl = args.clone();\n"
            "    consume(copy.as_va_list());\n"
            "}\n"
        )
        self.assertIn("let mut copy: ::core::ffi::VaList = args.clone();", output)
        self.assertIn("consume(copy.clone());", output)
        self.assertNotIn("VaListImpl", output)
        self.assertNotIn("as_va_list", output)

    def test_integer_to_bool_cast_compares_with_zero(self) -> None:
        output = self.transform(
            "fn f(value: i32) { let flag: bool = (value & 1) as bool; }\n"
        )
        self.assertIn("let flag: bool = (value & 1) != 0;", output)

    def test_asm_cast_output_uses_short_lived_raw_pointer_references(self) -> None:
        output = self.transform(
            'unsafe extern "C" fn swap(mut val: u32) -> u32 {\n'
            '    let fresh1 = &mut val;\n'
            '    let fresh2;\n'
            '    let fresh3 = val;\n'
            '    asm!("bswap {0}", inlateout(reg) '
            'c2rust_asm_casts::AsmCast::cast_in(fresh1, fresh3) => fresh2);\n'
            '    c2rust_asm_casts::AsmCast::cast_out(fresh1, fresh3, fresh2);\n'
            '    val\n'
            '}\n'
        )
        self.assertIn("let fresh1 = &raw mut val;", output)
        self.assertIn("AsmCast::cast_in(&mut *fresh1, fresh3)", output)
        self.assertIn("AsmCast::cast_out(&mut *fresh1, fresh3, fresh2)", output)

    def test_redundant_cast_of_bool_returning_call_is_removed(self) -> None:
        output = self.transform(
            "extern \"C\" { fn predicate(value: Option<unsafe extern \"C\" fn(i32) -> bool>) -> bool; }\n"
            "fn f(callback: Option<unsafe extern \"C\" fn(i32) -> bool>) {\n"
            "    let flag: bool = predicate(callback) as bool;\n"
            "}\n"
        )
        self.assertIn("let flag: bool = predicate(callback);", output)

    def test_checked_arithmetic_uses_mixed_type_compatibility_helper(self) -> None:
        output = self.transform(
            "fn f(left: i64, right: i32) {\n"
            "    let (value, overflow) = left.overflowing_add(right);\n"
            "    consume(value, overflow);\n"
            "}\n"
        )
        self.assertIn("crate::rustbox_c2rust_ckd_add(left, right)", output)
        self.assertNotIn(".overflowing_add(", output)

    def test_checked_arithmetic_rewrite_handles_multiline_operands(self) -> None:
        output = self.transform(
            "fn f(left: i64, right: i32) {\n"
            "    let (value, overflow) = left\n"
            "        .overflowing_mul(\n"
            "            right.wrapping_add(1),\n"
            "        );\n"
            "    consume(value, overflow);\n"
            "}\n"
        )
        self.assertIn("crate::rustbox_c2rust_ckd_mul(left,", output)
        self.assertIn("right.wrapping_add(1)", output)
        self.assertNotIn(".overflowing_mul(", output)

    def test_checked_arithmetic_support_preserves_wrapped_destination(self) -> None:
        support = MODULE.CHECKED_ARITHMETIC_SUPPORT
        self.assertIn("left.wrapping_add(right)", support)
        self.assertIn("left.wrapping_sub(right)", support)
        self.assertIn("left.wrapping_mul(right)", support)
        self.assertIn("O::rustbox_from_i128_wrapping(low_bits)", support)
        self.assertIn("value < O::MIN_I128", support)
        self.assertIn("O::MAX_I128 < value", support)

    def test_archive_override_keeps_program_export_and_mangles_library_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            program = root / "src/src/util.rs"
            library = root / "src/lib/xalloc_die.rs"
            program.parent.mkdir(parents=True)
            library.parent.mkdir(parents=True)
            definition = '#[no_mangle]\npub unsafe extern "C" fn xalloc_die() {}\n'
            program.write_text(definition, encoding="utf-8")
            library.write_text(definition, encoding="utf-8")
            changes = MODULE.deduplicate_no_mangle_functions(root)
            self.assertEqual(changes, [{
                "symbol": "xalloc_die",
                "kept": "src/src/util.rs",
                "mangled": "src/lib/xalloc_die.rs",
            }])
            self.assertIn("#[no_mangle]", program.read_text(encoding="utf-8"))
            self.assertNotIn("#[no_mangle]", library.read_text(encoding="utf-8"))

    def test_separate_program_globals_receive_private_linkage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "src/bc/global.rs"
            second = root / "src/dc/numeric.rs"
            first.parent.mkdir(parents=True)
            second.parent.mkdir(parents=True)
            definition = "#[no_mangle]\npub static mut std_only: i32 = 0;\n"
            first.write_text(definition, encoding="utf-8")
            second.write_text(definition, encoding="utf-8")
            changes = MODULE.deduplicate_no_mangle_statics(root)
            self.assertEqual(changes, [{
                "symbol": "std_only",
                "kept": "src/bc/global.rs",
                "mangled": "src/dc/numeric.rs",
            }])
            self.assertIn("#[no_mangle]", first.read_text(encoding="utf-8"))
            self.assertNotIn("#[no_mangle]", second.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
