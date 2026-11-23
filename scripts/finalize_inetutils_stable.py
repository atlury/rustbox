#!/usr/bin/env python3
"""Apply Inetutils-specific stable-Rust ABI boundary decisions."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rewrite_exact(path: Path, old: str, new: str, expected: int) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != expected:
        raise RuntimeError(f"{path}: expected {expected} exact rewrites")
    before = sha256(path)
    path.write_text(text.replace(old, new), encoding="utf-8")
    return {
        "path": path.name,
        "occurrences": expected,
        "before_sha256": before,
        "after_sha256": sha256(path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--crate", required=True, type=Path)
    args = parser.parse_args()
    crate = args.crate.resolve()
    if not (crate / "rustbox-modernization.json").is_file():
        raise RuntimeError("missing Inetutils stable modernization manifest")

    barrier = crate / "src/lib/memset_explicit.rs"
    barrier_change = rewrite_exact(
        barrier,
        'asm!("\\n", in (reg) & s, options(preserves_flags, att_syntax));',
        'asm!("/* {0} */", in (reg) & s, options(preserves_flags, att_syntax));',
        1,
    )
    barrier_change.update({
        "operation": "name the input operand in the empty compiler barrier",
        "semantic_basis": (
            "the generated assembly remains an empty comment while Rust retains "
            "the input dependency that implements gnulib's compiler barrier"
        ),
    })

    primes = crate / "src/lib/gl_hash_set.rs"
    prime_change = rewrite_exact(
        primes,
        "as ::core::ffi::c_ulong,",
        "as ::core::ffi::c_ulong as size_t,",
        126,
    )
    prime_change.update({
        "operation": "coerce unsigned-long literals to the declared size_t array type",
        "semantic_basis": (
            "unsigned long and size_t have identical width and value representation "
            "on the pinned x86_64 GNU target"
        ),
    })
    sentinel_change = rewrite_exact(
        primes,
        "    SIZE_MAX,\n];",
        "    SIZE_MAX as size_t,\n];",
        1,
    )
    sentinel_change.update({
        "operation": "coerce the unsigned-long sentinel to the declared size_t array type",
        "semantic_basis": prime_change["semantic_basis"],
    })

    ftpd = crate / "src/ftpd/ftpd.rs"
    ftpd_type_change = rewrite_exact(
        ftpd,
        '#[export_name = "type"]\npub static mut type_0:',
        "pub static mut type_0:",
        1,
    )
    ftpd_type_change.update({
        "operation": "mangle FTPD's program-local C `type` variable",
        "semantic_basis": (
            "FTPD references this static directly; its export collides with FTP's "
            "unrelated variable only in the combined translation-audit crate"
        ),
    })

    library = crate / "lib.rs"
    module = crate / "src/lib/printf_args.rs"
    declaration = "pub mod printf_args;\n"
    library_text = library.read_text(encoding="utf-8")
    translated = module.read_text(encoding="utf-8")
    if library_text.count(declaration) != 1:
        raise RuntimeError("Inetutils printf_args module declaration is not unique")
    if translated.count("next_arg::<::f128::f128>()") != 1:
        raise RuntimeError("Inetutils long-double va_arg boundary changed")
    library_before = sha256(library)
    library.write_text(library_text.replace(declaration, ""), encoding="utf-8")
    boundary_change = {
        "path": "lib.rs",
        "before_sha256": library_before,
        "after_sha256": sha256(library),
        "omitted_rust_module": "src/lib/printf_args.rs",
        "canonical_c_residue": "lib/printf-args.c",
        "operation": "retain canonical C for gnulib long-double variadic extraction",
        "semantic_basis": (
            "stable Rust's sealed VaArgSafe trait cannot represent the x86_64 "
            "SysV C long-double va_arg operation emitted as f128 by C2Rust"
        ),
    }

    manifest = {
        "schema": 1,
        "target": "x86_64-unknown-linux-gnu",
        "changes": [
            barrier_change,
            prime_change,
            sentinel_change,
            ftpd_type_change,
            boundary_change,
        ],
    }
    output = crate / "rustbox-inetutils-stable.json"
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "canonical_c_sources": 1,
        "rust_sources": 287,
        "stable_representation_repairs": 128,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
