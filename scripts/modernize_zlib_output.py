#!/usr/bin/env python3
"""Apply zlib-specific, semantics-preserving stable Rust modernization."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path


TYPE_ANCHOR = """pub type compress_func = Option<
    unsafe extern \"C\" fn(*mut deflate_state, ::core::ffi::c_int) -> block_state,
>;
"""
TYPE_REPLACEMENT = TYPE_ANCHOR + """
#[inline]
fn rustbox_compress_func_eq(left: compress_func, right: compress_func) -> bool {
    match (left, right) {
        (Some(left), Some(right)) => ::core::ptr::fn_addr_eq(left, right),
        (None, None) => true,
        _ => false,
    }
}
"""
COMPARE_ANCHOR = "func != configuration_table[level as usize].func"
COMPARE_REPLACEMENT = (
    "!rustbox_compress_func_eq(func, configuration_table[level as usize].func)"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.input.resolve()
    output = args.output.resolve()
    if source == output or output.parent != source.parent or not output.name.endswith("-stable"):
        raise RuntimeError("output must be a distinct *-stable sibling")
    target = source / "src/deflate.rs"
    before = target.read_text()
    if before.count(TYPE_ANCHOR) != 1 or before.count(COMPARE_ANCHOR) != 1:
        raise RuntimeError("zlib function-pointer modernization precondition failed")

    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    try:
        shutil.copytree(source, staged, ignore=shutil.ignore_patterns("target", "Cargo.lock"))
        staged_target = staged / "src/deflate.rs"
        after = before.replace(TYPE_ANCHOR, TYPE_REPLACEMENT).replace(
            COMPARE_ANCHOR, COMPARE_REPLACEMENT
        )
        staged_target.write_text(after)
        record = {
            "schema": 1,
            "rule": "Option<C function pointer> identity via core::ptr::fn_addr_eq",
            "source": "src/deflate.rs",
            "before_sha256": sha256(target),
            "after_sha256": sha256(staged_target),
            "replacement_count": 1,
            "hand_edits": 0,
        }
        (staged / "rustbox-zlib-modernization.json").write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n"
        )
        if output.exists():
            shutil.rmtree(output)
        staged.rename(output)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    print(json.dumps(record, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
