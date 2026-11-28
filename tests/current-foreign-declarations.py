#!/usr/bin/env python3
"""Exercise temporary diagnostic names with rustc, then select spans on the same byte layout."""
# SPDX-License-Identifier: 0BSD
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_current_foreign_declarations import apply_spans, diagnostic_names
from check_cargo_private_inlines import digest
from verify_c_string_sources import syntax_tool


def main():
    selector = syntax_tool("foreign-declarations")
    with TemporaryDirectory() as scratch:
        crate = Path(scratch)
        (crate / "lib.rs").write_text("mod leaf; mod nested;")
        leaf = crate / "leaf.rs"
        original = b'''extern "C" {
    fn __unused(x: *const u8);
    static __UNUSED_STATIC: *const u8;
    fn __used(x: *const u8);
    fn __collision(x: *const u8);
    fn z_collision(x: *const u8);
    #[link_name = "foreign"]
    fn __attributed(x: *const u8);
    pub fn __public(x: *const u8);
}
pub unsafe fn run(x: *const u8) { __used(x) }
'''
        leaf.write_bytes(original)
        nested = crate / "nested.rs"
        nested.write_text('mod child {}\nextern "C" {\n    fn __nested(x: *const u8);\n}\n')
        inputs = {p.name: digest(p) for p in crate.glob("*.rs")}
        with diagnostic_names(crate, inputs):
            result = subprocess.run(["rustc", "--crate-type", "lib", "--emit=metadata", "-A", "warnings",
                                     "--force-warn", "dead_code", "--error-format=json", "lib.rs"],
                                    cwd=crate, capture_output=True, check=True)
            spans = json.loads(subprocess.check_output([selector], cwd=crate, input=result.stderr))
        if leaf.read_bytes() != original or set(spans) != {"leaf.rs"}:
            raise AssertionError("source restoration or leaf-module filtering failed")
        changes, report = apply_spans(crate, inputs, spans, selector=selector)
        selected = [original[start:end] for start, end in spans["leaf.rs"]]
        # The control name z_collision is itself dead and eligible. Its presence
        # prevents the underscore-prefixed declaration from being probed.
        expected = [b"fn __unused(x: *const u8);", b"static __UNUSED_STATIC: *const u8;",
                    b"fn z_collision(x: *const u8);"]
        if selected != expected or report["raw_pointer_types_removed"] != 3:
            raise AssertionError(f"unexpected selected declarations: {selected}")
        leaf.write_bytes(changes["leaf.rs"])
        subprocess.run(["rustc", "--crate-type", "lib", "--emit=metadata", "-A", "warnings", "lib.rs"],
                       cwd=crate, check=True)
    print("Compiler spans, source restoration, exclusions and the rebuilt library passed")


if __name__ == "__main__":
    main()
