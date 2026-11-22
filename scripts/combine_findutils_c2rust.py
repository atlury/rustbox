#!/usr/bin/env python3
"""Combine bounded Findutils C2Rust outputs into one deterministic crate."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path


PREAMBLE = """#![allow(dead_code)]
#![allow(non_camel_case_types)]
#![allow(non_snake_case)]
#![allow(non_upper_case_globals)]
#![allow(unused_assignments)]
#![allow(unused_mut)]
#![feature(c_variadic)]
#![feature(extern_types)]
#![feature(label_break_value)]
#![feature(linkage)]
#![feature(raw_ref_op)]

#[macro_use]
extern crate c2rust_bitfields;
extern crate f128;
#[macro_use]
extern crate num_traits;
extern crate libc;

"""

CARGO = """[workspace]
members = []

[package]
name = "findutils_4_10_0_combined"
authors = ["C2Rust", "Rustbox"]
version = "0.0.0"
publish = false
edition = "2021"
autobins = false

[lib]
name = "findutils_4_10_0_combined"
path = "lib.rs"
crate-type = ["staticlib", "rlib"]

[dependencies]
c2rust-bitfields = "0.22.1"
f128 = "0.2"
libc = "0.2"
num-traits = "0.2"
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exclude", action="append", default=[])
    args = parser.parse_args()
    source = args.input.resolve()
    output = args.output.resolve()
    batches = sorted(path for path in source.glob("batch-*") if path.is_dir())
    if len(batches) != 8 or output == source or output.is_symlink():
        raise RuntimeError("Findutils C2Rust batch surface changed")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    staged_sources = staged / "src"
    staged_sources.mkdir(parents=True)
    excluded = set(args.exclude)
    modules: dict[str, dict[str, object]] = {}
    declaration_maps = 0
    try:
        for batch in batches:
            for rust in sorted((batch / "src").rglob("*.rs")):
                module = rust.stem
                if module in excluded:
                    continue
                if module in modules:
                    raise RuntimeError(f"duplicate flattened Findutils module: {module}")
                target = staged_sources / rust.name
                shutil.copy2(rust, target)
                declaration = rust.with_suffix(".c_decls.json")
                has_declaration = declaration.is_file()
                if has_declaration:
                    shutil.copy2(declaration, staged_sources / declaration.name)
                    declaration_maps += 1
                modules[module] = {
                    "batch": batch.name,
                    "source": str(rust.relative_to(batch)),
                    "sha256": sha256(target),
                    "declaration_map": has_declaration,
                }
        expected_modules = 193 - len(excluded)
        expected_maps = 192 - len(excluded)
        if (
            len(modules) != expected_modules
            or declaration_maps != expected_maps
            or "parse_datetime" not in modules
        ):
            raise RuntimeError("combined Findutils module or declaration-map count changed")
        if modules["parse_datetime"]["declaration_map"]:
            raise RuntimeError("parse-datetime declaration-map exception changed")

        declarations = "".join(
            f'#[path = "src/{name}.rs"]\npub mod {name};\n'
            for name in sorted(modules)
        )
        (staged / "lib.rs").write_text(PREAMBLE + declarations)
        (staged / "Cargo.toml").write_text(CARGO)
        (staged / "build.rs").write_text("fn main() {}\n")
        (staged / "rust-toolchain.toml").write_text(
            '[toolchain]\nchannel = "nightly-2023-04-15"\ncomponents = ["rustfmt"]\n'
        )
        manifest = {
            "schema": 1,
            "batches": len(batches),
            "modules": len(modules),
            "declaration_maps": declaration_maps,
            "declaration_map_exceptions": ["parse_datetime"],
            "excluded_modules": sorted(excluded),
            "module_inventory": modules,
        }
        (staged / "rustbox-combination.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        if output.exists():
            shutil.rmtree(output)
        staged.rename(output)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)

    print(json.dumps({
        "batches": 8, "declaration_maps": declaration_maps,
        "excluded_modules": sorted(excluded), "modules": len(modules),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
