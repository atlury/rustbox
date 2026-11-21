#!/usr/bin/env python3
"""Apply narrow, audited repairs to C2Rust's XZ 5.8.4 output."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


READ_MEMCPY = """memcpy(
        &raw mut num as *mut ::core::ffi::c_void,
        buf,"""
READ_MEMCPY_FIXED = """memcpy(
        &raw mut num as *mut ::core::ffi::c_void,
        buf as *const ::core::ffi::c_void,"""
WRITE_MEMCPY = """memcpy(
        buf,
        &raw mut num as *const ::core::ffi::c_void,"""
WRITE_MEMCPY_FIXED = """memcpy(
        buf as *mut ::core::ffi::c_void,
        &raw mut num as *const ::core::ffi::c_void,"""


def digest(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def repair_memcpy(root: Path) -> list[dict[str, object]]:
    changes = []
    read_total = 0
    write_total = 0
    for path in sorted(root.rglob("*.rs")):
        before = path.read_text()
        reads = before.count(READ_MEMCPY)
        writes = before.count(WRITE_MEMCPY)
        if not reads and not writes:
            continue
        after = before.replace(READ_MEMCPY, READ_MEMCPY_FIXED).replace(
            WRITE_MEMCPY, WRITE_MEMCPY_FIXED
        )
        path.write_text(after)
        read_total += reads
        write_total += writes
        changes.append(
            {
                "path": path.relative_to(root).as_posix(),
                "before_sha256": digest(before),
                "after_sha256": digest(after),
                "const_void_pointer_casts": reads,
                "mut_void_pointer_casts": writes,
            }
        )
    if read_total != 237 or write_total != 237:
        raise RuntimeError(
            f"XZ aligned memcpy helper count changed: {read_total}/{write_total}"
        )
    return changes


def repair_options(root: Path) -> dict[str, object]:
    path = root / "src/xz/options.rs"
    before = path.read_text()
    function_start = before.index('unsafe extern "C" fn parse_options(')
    function_end = before.index('\nunsafe extern "C" fn set_delta(', function_start)
    function = before[function_start:function_end]
    if len(re.findall(r"\bopts\b", function)) != 11:
        raise RuntimeError("XZ parse_options binding count changed")
    function = re.sub(r"\bopts\b", "option_maps", function)
    text = before[:function_start] + function + before[function_end:]

    marker = '#[no_mangle]\npub unsafe extern "C" fn options_lzma('
    insert_at = text.index(marker)
    hoisted = []
    for name, length in (("modes", 3), ("mfs", 6)):
        pattern = re.compile(
            rf"    static mut {name}: \[name_id_map; {length}\] = \[\n.*?^    \];\n",
            re.MULTILINE | re.DOTALL,
        )
        matches = list(pattern.finditer(text))
        if len(matches) != 1:
            raise RuntimeError(f"XZ local {name} option table changed")
        block = matches[0].group(0)
        text = text[: matches[0].start()] + text[matches[0].end() :]
        hoisted.append("\n".join(line[4:] for line in block.splitlines()) + "\n")
        insert_at = text.index(marker)
    text = text[:insert_at] + "".join(hoisted) + text[insert_at:]
    path.write_text(text)
    return {
        "path": path.relative_to(root).as_posix(),
        "before_sha256": digest(before),
        "after_sha256": digest(text),
        "renamed_shadowing_parameter": "opts -> option_maps",
        "hoisted_static_option_tables": ["modes", "mfs"],
    }


def repair_integer_bools(root: Path) -> dict[str, object]:
    path = root / "src/xz/list.rs"
    before = path.read_text()
    needle = "as ::core::ffi::c_int) as bool"
    count = before.count(needle)
    if count != 4:
        raise RuntimeError(f"XZ integer-to-bool repair count changed: {count}")
    after = before.replace(needle, "as ::core::ffi::c_int) != 0")
    path.write_text(after)
    return {
        "path": path.relative_to(root).as_posix(),
        "before_sha256": digest(before),
        "after_sha256": digest(after),
        "integer_to_bool_repairs": count,
    }


def repair_size_arithmetic(root: Path) -> list[dict[str, object]]:
    replacements = {
        "src/liblzma/common/block_encoder.rs": [
            (
                "(in_size as lzma_vli).wrapping_sub(*in_pos)",
                "in_size.wrapping_sub(*in_pos) as lzma_vli",
            ),
        ],
        "src/liblzma/common/file_info.rs": [
            (
                "(*in_pos).wrapping_sub(in_start as uint64_t)",
                "(*in_pos).wrapping_sub(in_start) as uint64_t",
            ),
            (
                "(in_size as uint64_t).wrapping_sub(*in_pos)",
                "in_size.wrapping_sub(*in_pos) as uint64_t",
            ),
        ],
        "src/liblzma/common/index_decoder.rs": [
            (
                "(in_size as uint64_t).wrapping_sub(*in_pos)",
                "in_size.wrapping_sub(*in_pos) as uint64_t",
            ),
        ],
        "src/liblzma/common/microlzma_encoder.rs": [
            (
                "(out_size as uint64_t).wrapping_sub(*out_pos)",
                "out_size.wrapping_sub(*out_pos) as uint64_t",
            ),
        ],
    }
    changes = []
    for relative, pairs in replacements.items():
        path = root / relative
        before = path.read_text()
        after = before
        for old, new in pairs:
            if after.count(old) != 1:
                raise RuntimeError(f"XZ size arithmetic changed in {relative}: {old}")
            after = after.replace(old, new)
        path.write_text(after)
        changes.append(
            {
                "path": relative,
                "before_sha256": digest(before),
                "after_sha256": digest(after),
                "size_arithmetic_repairs": len(pairs),
                "semantics": "subtract in size_t, then convert to uint64_t",
            }
        )
    return changes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--crate", type=Path, required=True)
    args = parser.parse_args()
    root = args.crate.resolve()
    if not (root / "Cargo.toml").is_file() or root.name != "xz-5.8.4-stable":
        raise RuntimeError("expected the stable XZ 5.8.4 translation crate")
    manifest = {
        "schema": 1,
        "package": "XZ Utils 5.8.4",
        "repairs": [
            *repair_memcpy(root),
            repair_options(root),
            repair_integer_bools(root),
            *repair_size_arithmetic(root),
        ],
    }
    output = root / "rustbox-xz-repairs.json"
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
