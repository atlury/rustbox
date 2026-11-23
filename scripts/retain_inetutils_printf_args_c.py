#!/usr/bin/env python3
"""Retain canonical gnulib printf-args.c at stable Rust's f128 va_arg boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--crate", required=True, type=Path)
    args = parser.parse_args()
    crate = args.crate.resolve()
    library = crate / "lib.rs"
    translated = crate / "src/lib/printf_args.rs"
    declaration = "pub mod printf_args;\n"
    library_text = library.read_text(encoding="utf-8")
    translated_text = translated.read_text(encoding="utf-8")
    if library_text.count(declaration) != 1:
        raise RuntimeError("printf_args module declaration is not unique")
    if translated_text.count("next_arg::<::f128::f128>()") != 1:
        raise RuntimeError("long-double va_arg boundary changed")
    before = sha256(library)
    library.write_text(library_text.replace(declaration, ""), encoding="utf-8")
    manifest = {
        "schema": 1,
        "target": "x86_64-unknown-linux-gnu",
        "path": "lib.rs",
        "before_sha256": before,
        "after_sha256": sha256(library),
        "omitted_rust_module": "src/lib/printf_args.rs",
        "canonical_c_residue": "lib/printf-args.c",
        "operation": "retain canonical C for gnulib long-double variadic extraction",
        "semantic_basis": (
            "stable Rust's sealed VaArgSafe trait cannot represent the x86_64 "
            "SysV C long-double va_arg operation emitted as f128 by C2Rust"
        ),
    }
    output = crate / "rustbox-inetutils-program-boundary.json"
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"canonical_c_sources": 1, "omitted_rust_modules": 1}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
