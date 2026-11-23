#!/usr/bin/env python3
"""Apply GNU Bison-specific stable-Rust ABI boundary decisions."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repair_prime_table(crate: Path, path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    start = text.find("static mut primes: [size_t; 232] = [")
    if start < 0:
        raise RuntimeError(f"missing prime-table anchor: {path}")
    end = text.find("\n];", start)
    if end < 0:
        raise RuntimeError(f"unterminated prime table: {path}")
    before = text[start:end]
    old = " as ::core::ffi::c_ulong,"
    if before.count(old) != 126:
        raise RuntimeError(f"prime-table cast closure changed: {path}")
    after = before.replace(old, " as size_t,")
    if after.count("    SIZE_MAX,") != 1:
        raise RuntimeError(f"prime-table sentinel closure changed: {path}")
    after = after.replace("    SIZE_MAX,", "    SIZE_MAX as size_t,")
    old_digest = sha256(path)
    path.write_text(text[:start] + after + text[end:], encoding="utf-8")
    return {
        "path": path.relative_to(crate).as_posix(),
        "before_sha256": old_digest,
        "after_sha256": sha256(path),
        "operation": (
            "give 126 LP64 prime literals and the SIZE_MAX sentinel their "
            "declared size_t type"
        ),
        "semantic_basis": (
            "the audited x86_64 GNU target defines unsigned long and size_t as "
            "the same 64-bit unsigned integer representation"
        ),
    }


def retain_variadic_c_boundary(crate: Path) -> dict[str, object]:
    library = crate / "lib.rs"
    text = library.read_text(encoding="utf-8")
    old_digest = sha256(library)
    modules = ("printf_args", "printf_frexpl", "printf_parse", "vasnprintf")
    for module in modules:
        declaration = f"pub mod {module};\n"
        if text.count(declaration) != 1:
            raise RuntimeError(f"missing unique module declaration: {module}")
        text = text.replace(declaration, "")
    library.write_text(text, encoding="utf-8")
    return {
        "path": library.relative_to(crate).as_posix(),
        "before_sha256": old_digest,
        "after_sha256": sha256(library),
        "omitted_rust_modules": list(modules),
        "canonical_c_residue": [
            "lib/printf-args.c",
            "lib/printf-frexpl.c",
            "lib/printf-parse.c",
            "lib/vasnprintf.c",
        ],
        "operation": "retain canonical C for the variadic long-double boundary",
        "semantic_basis": (
            "stable Rust's sealed VaArgSafe trait cannot represent the x86_64 "
            "SysV C long-double va_arg operation emitted as f128 by C2Rust"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--crate", required=True, type=Path)
    args = parser.parse_args()
    crate = args.crate.resolve()
    for required in ("rustbox-cross-module-types.json", "rustbox-modernization.json"):
        if not (crate / required).is_file():
            raise RuntimeError(f"missing preparation manifest: {required}")

    changes = [
        repair_prime_table(crate, crate / "src/lib/gl_hash_map.rs"),
        repair_prime_table(crate, crate / "src/lib/gl_rbtreehash_list.rs"),
        retain_variadic_c_boundary(crate),
    ]
    manifest = {
        "schema": 1,
        "target": "x86_64-unknown-linux-gnu",
        "changes": changes,
    }
    output = crate / "rustbox-bison-stable.json"
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "canonical_c_sources": 4,
        "prime_table_casts": 254,
        "rust_sources": 148,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
