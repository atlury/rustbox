#!/usr/bin/env python3
"""Apply GNU tar-specific, deterministic stable-Rust boundary decisions."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_exact(path: Path, before: str, after: str) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if text.count(before) != 1:
        raise RuntimeError(f"stable-finalization precondition failed: {path}")
    old_digest = sha256(path)
    path.write_text(text.replace(before, after), encoding="utf-8")
    return {
        "path": str(path),
        "before_sha256": old_digest,
        "after_sha256": sha256(path),
    }


def repair_name_ownership(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    old_digest = sha256(path)
    helper_anchor = """}
static mut namelist: *mut name = ::core::ptr::null::<name>() as *mut name;
"""
    helper = """}
unsafe fn rustbox_release_namelist() {
    while !namelist.is_null() {
        let next = (*namelist).next;
        free_name(namelist);
        namelist = next;
    }
    nametail = ::core::ptr::null_mut::<name>();
}
static mut namelist: *mut name = ::core::ptr::null::<name>() as *mut name;
"""
    if text.count(helper_anchor) != 1:
        raise RuntimeError(f"name-list helper precondition failed: {path}")
    text = text.replace(helper_anchor, helper)

    discarded = """        {
            unconsumed_option_push(elt);
        }
    } else {
"""
    released = """        {
            unconsumed_option_push(elt);
        } else {
            free(elt as *mut ::core::ffi::c_void);
        }
    } else {
"""
    if text.count(discarded) != 1:
        raise RuntimeError(f"name-element ownership precondition failed: {path}")
    text = text.replace(discarded, released)

    abandoned = """    namelist = ::core::ptr::null_mut::<name>();
    nametail = ::core::ptr::null_mut::<name>();
"""
    if text.count(abandoned) != 2:
        raise RuntimeError(f"abandoned name-list precondition failed: {path}")
    text = text.replace(abandoned, "    rustbox_release_namelist();\n")
    abandoned_nested = """            namelist = ::core::ptr::null_mut::<name>();
            nametail = ::core::ptr::null_mut::<name>();
"""
    if text.count(abandoned_nested) != 1:
        raise RuntimeError(f"empty-name list precondition failed: {path}")
    text = text.replace(
        abandoned_nested, "            rustbox_release_namelist();\n"
    )
    path.write_text(text, encoding="utf-8")
    return {
        "path": str(path),
        "before_sha256": old_digest,
        "after_sha256": sha256(path),
        "operation": (
            "release consumed non-create positional elements and free both "
            "name lists before discarding their heads"
        ),
        "semantic_basis": (
            "the canonical code explicitly discards these allocations only "
            "because a standalone process is about to exit; freeing them does "
            "not change archive, diagnostic, status, or filesystem behavior"
        ),
        "released_sites": 4,
    }


def route_rmt_program_metadata(path: Path) -> dict[str, object]:
    """Make rmt use gnulib argp's one shared metadata definition."""
    text = path.read_text(encoding="utf-8")
    old_digest = sha256(path)
    definitions = """pub static mut argp_program_version: *const ::core::ffi::c_char = b"rmt (GNU tar) 1.35\\0"
    as *const u8 as *const ::core::ffi::c_char;
pub static mut argp_program_bug_address: *const ::core::ffi::c_char = b"<bug-tar@gnu.org>\\0"
    as *const u8 as *const ::core::ffi::c_char;
"""
    if text.count(definitions) != 1:
        raise RuntimeError(f"rmt metadata-definition precondition failed: {path}")
    text = text.replace(definitions, "")
    extern_anchor = """    fn safe_read(
        fd: ::core::ffi::c_int,
        buf: *mut ::core::ffi::c_void,
        count: size_t,
    ) -> size_t;
}
"""
    extern_metadata = """    fn safe_read(
        fd: ::core::ffi::c_int,
        buf: *mut ::core::ffi::c_void,
        count: size_t,
    ) -> size_t;
    static mut argp_program_version: *const ::core::ffi::c_char;
    static mut argp_program_bug_address: *const ::core::ffi::c_char;
}
"""
    if text.count(extern_anchor) != 1:
        raise RuntimeError(f"rmt metadata-extern precondition failed: {path}")
    path.write_text(text.replace(extern_anchor, extern_metadata), encoding="utf-8")
    return {
        "path": str(path),
        "before_sha256": old_digest,
        "after_sha256": sha256(path),
        "operation": "route rmt metadata through gnulib argp globals",
        "semantic_basis": (
            "C weak-default semantics require one shared argp metadata object; "
            "the translator emitted an additional strong rmt definition whose "
            "archive selection differed in the unified link"
        ),
    }


def repair_rmt_program_metadata(path: Path) -> dict[str, object]:
    """Route and initialize rmt metadata independent of archive selection."""
    old_digest = sha256(path)
    route_rmt_program_metadata(path)
    before = """pub unsafe extern \"C\" fn rustbox_rmt_main(
    mut argc: ::core::ffi::c_int,
    mut argv: *mut *mut ::core::ffi::c_char,
) -> ::core::ffi::c_int {
    let mut buf: *mut ::core::ffi::c_char = ::core::ptr::null_mut::<
"""
    after = """pub unsafe extern \"C\" fn rustbox_rmt_main(
    mut argc: ::core::ffi::c_int,
    mut argv: *mut *mut ::core::ffi::c_char,
) -> ::core::ffi::c_int {
    argp_program_version = b\"rmt (GNU tar) 1.35\\0\" as *const u8
        as *const ::core::ffi::c_char;
    argp_program_bug_address = b\"<bug-tar@gnu.org>\\0\" as *const u8
        as *const ::core::ffi::c_char;
    let mut buf: *mut ::core::ffi::c_char = ::core::ptr::null_mut::<
"""
    replace_exact(path, before, after)
    return {
        "path": str(path),
        "before_sha256": old_digest,
        "after_sha256": sha256(path),
        "operation": "route and initialize rmt argp metadata",
        "semantic_basis": (
            "canonical rmt writes gnulib argp's weak-default metadata; routing "
            "the translated entry through that single private definition makes "
            "behavior independent of static-archive member selection"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--crate", required=True, type=Path)
    parser.add_argument("--repair-rmt-globals-only", action="store_true")
    parser.add_argument("--route-rmt-globals-only", action="store_true")
    args = parser.parse_args()
    crate = args.crate.resolve()
    if not (crate / "rustbox-modernization.json").is_file():
        raise RuntimeError("input is not a mechanically modernized C2Rust crate")

    if args.repair_rmt_globals_only:
        change = repair_rmt_program_metadata(crate / "src/rmt/rmt.rs")
        output = crate / "rustbox-tar-stable.json"
        manifest = json.loads(output.read_text(encoding="utf-8"))
        manifest["transformations"].append(change)
        output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        print(json.dumps(change, sort_keys=True))
        return 0
    if args.route_rmt_globals_only:
        change = route_rmt_program_metadata(crate / "src/rmt/rmt.rs")
        output = crate / "rustbox-tar-stable.json"
        manifest = json.loads(output.read_text(encoding="utf-8"))
        manifest["transformations"].append(change)
        output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        print(json.dumps(change, sort_keys=True))
        return 0

    tar_change = replace_exact(
        crate / "src/src/tar.rs",
        "u == record_size.wrapping_div(BLOCKSIZE as uintmax_t)",
        "u == record_size.wrapping_div(BLOCKSIZE as size_t) as uintmax_t",
    )
    tar_change.update({
        "operation": (
            "give wrapping_div the size_t receiver type and explicitly restore "
            "the canonical comparison's uintmax_t common type"
        ),
        "semantic_basis": (
            "BLOCKSIZE is the positive constant 512, representable without change "
            "in both uintmax_t and size_t on the audited LP64 target"
        ),
    })
    name_change = repair_name_ownership(crate / "src/src/names.rs")
    rmt_change = repair_rmt_program_metadata(crate / "src/rmt/rmt.rs")

    modules = ("human", "printf_args", "printf_parse", "vasnprintf")
    library = crate / "lib.rs"
    text = library.read_text(encoding="utf-8")
    before_digest = sha256(library)
    for module in modules:
        declaration = f"pub mod {module};\n"
        if text.count(declaration) != 1:
            raise RuntimeError(f"missing unique module declaration: {module}")
        text = text.replace(declaration, "")
    library.write_text(text, encoding="utf-8")

    manifest = {
        "schema": 1,
        "target": "x86_64-unknown-linux-gnu",
        "transformations": [tar_change, name_change, rmt_change],
        "canonical_c_residue": [
            "gnu/human.c",
            "gnu/printf-args.c",
            "gnu/printf-parse.c",
            "gnu/vasnprintf.c",
        ],
        "omitted_rust_modules": list(modules),
        "lib_before_sha256": before_digest,
        "lib_after_sha256": sha256(library),
        "residue_reason": (
            "x86_64 SysV long double and variadic va_list ABI must remain in "
            "canonical C; Rust's stable VaList does not accept the translator's "
            "f128 wrapper and the wrapper is not an ABI substitute for C long double"
        ),
    }
    output = crate / "rustbox-tar-stable.json"
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
