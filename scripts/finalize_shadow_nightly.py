#!/usr/bin/env python3
"""Apply asserted representation repairs to the complete Shadow C2Rust crate."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


USIZE_FILES = (
    "src/lib/addgrps.rs", "src/lib/env.rs", "src/lib/subordinateio.rs",
    "src/lib/xgetgrgid.rs", "src/lib/xgetgrnam.rs", "src/lib/xgetpwnam.rs",
    "src/lib/xgetpwuid.rs", "src/lib/xgetspnam.rs", "src/lib/xprefix_getpwnam.rs",
    "src/src/newgrp.rs",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace(path: Path, old: str, new: str, expected: int, kind: str) -> dict[str, object]:
    text = path.read_text()
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"Shadow repair input changed: {path}: expected {expected}, found {count}")
    before = sha256(path)
    path.write_text(text.replace(old, new))
    return {
        "path": str(path), "kind": kind, "replacements": count,
        "before_sha256": before, "after_sha256": sha256(path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source = args.input.resolve()
    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(source, output, symlinks=True, ignore=shutil.ignore_patterns("target"))

    repairs = []
    old = "1 as ::core::ffi::c_int as ::core::ffi::c_ulong"
    for relative in USIZE_FILES:
        expected = 2 if relative == "src/lib/subordinateio.rs" else 1
        repairs.append(replace(
            output / relative, old, "1 as usize", expected,
            "match size_t fallback literal to translated usize parameter",
        ))
    repairs.append(replace(
        output / "src/lib/limits.rs",
        "l.overflowing_mul(multiplier)",
        "l.overflowing_mul(multiplier as rlim_t)", 1,
        "match limit multiplier to translated rlim_t",
    ))
    repairs.extend((
        replace(
            output / "src/src/faillog.rs",
            "uid.overflowing_mul(::core::mem::size_of::<faillog>())",
            "(uid as off_t).overflowing_mul(::core::mem::size_of::<faillog>() as off_t)", 1,
            "perform faillog offset multiplication in off_t",
        ),
        replace(
            output / "src/src/faillog.rs",
            "offset.overflowing_add(::core::mem::size_of::<faillog>())",
            "offset.overflowing_add(::core::mem::size_of::<faillog>() as off_t)", 1,
            "perform faillog size addition in off_t",
        ),
    ))
    nss = output / "src/lib/nss.rs"
    repairs.extend((
        replace(
            nss,
            "pub type atomic_bool = bool;",
            "pub type atomic_bool = u8;", 1,
            "represent C atomic_bool with its one-byte integer storage",
        ),
        replace(
            nss,
            "_Value: 0 as ::core::ffi::c_int != 0,",
            "_Value: 0 as atomic_bool,", 1,
            "initialize translated atomic_flag integer storage",
        ),
        replace(
            nss,
            "static mut nss_init_completed: atomic_bool = 0 as ::core::ffi::c_int != 0;",
            "static mut nss_init_completed: atomic_bool = 0 as atomic_bool;", 1,
            "initialize translated atomic_bool integer storage",
        ),
        replace(
            nss,
            "return ::core::intrinsics::atomic_load_seqcst(&raw mut nss_init_completed);",
            "return ::core::intrinsics::atomic_load_seqcst(&raw mut nss_init_completed) != 0;",
            1, "convert the atomic integer load back to C bool",
        ),
        replace(
            nss,
            """if ::core::intrinsics::atomic_xchg_seqcst(
        &raw mut nss_init_started._Value,
        1 as ::core::ffi::c_int != 0,
    ) {""",
            """if ::core::intrinsics::atomic_xchg_seqcst(
        &raw mut nss_init_started._Value,
        1 as atomic_bool,
    ) != 0 {""",
            1, "test the translated atomic_flag integer exchange",
        ),
        replace(
            nss,
            "while !::core::intrinsics::atomic_load_seqcst(&raw mut nss_init_completed) {",
            "while ::core::intrinsics::atomic_load_seqcst(&raw mut nss_init_completed) == 0 {",
            1, "test the translated atomic_bool integer load",
        ),
        replace(
            nss,
            """::core::intrinsics::atomic_store_seqcst(
            &raw mut nss_init_completed,
            1 as ::core::ffi::c_int != 0,
        );""",
            """::core::intrinsics::atomic_store_seqcst(
            &raw mut nss_init_completed,
            1 as atomic_bool,
        );""",
            1, "store true in translated atomic_bool integer storage",
        ),
        replace(
            nss,
            """::core::intrinsics::atomic_store_seqcst(
        &raw mut nss_init_completed,
        1 as ::core::ffi::c_int != 0,
    );""",
            """::core::intrinsics::atomic_store_seqcst(
        &raw mut nss_init_completed,
        1 as atomic_bool,
    );""",
            1, "store completion in translated atomic_bool integer storage",
        ),
    ))
    manifest = {
        "schema": 1,
        "source_modules": len(list(output.rglob("*.rs"))) - 2,
        "repair_sites": sum(int(item["replacements"]) for item in repairs),
        "repairs": repairs,
    }
    (output / "rustbox-repairs.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "repair_files": len({item["path"] for item in repairs}),
        "repair_sites": manifest["repair_sites"],
        "source_modules": manifest["source_modules"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
