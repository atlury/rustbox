#!/usr/bin/env python3
"""Combine bounded GNU Gawk C2Rust outputs into one deterministic crate."""

from __future__ import annotations

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
name = "{package}"
authors = ["C2Rust", "Rustbox"]
version = "0.0.0"
publish = false
edition = "2021"
autobins = false

[lib]
name = "{package}"
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
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scope", choices=("complete", "core"), default="complete")
    args = parser.parse_args()
    source, output = args.input.resolve(), args.output.resolve()
    batches = sorted(path for path in source.glob("batch-*") if path.is_dir())
    if len(batches) != 7 or output == source or output.is_symlink():
        raise RuntimeError("GNU Gawk C2Rust batch surface changed")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    staged_sources = staged / "src"
    staged_sources.mkdir(parents=True)
    modules = {}
    declaration_maps = 0
    try:
        for batch in batches:
            for rust in sorted((batch / "src").rglob("*.rs")):
                relative = rust.relative_to(batch / "src")
                if args.scope == "core" and (
                        "extension" in relative.parts or "awklib" in relative.parts or
                        relative == Path("support/pma.rs")):
                    continue
                module = rust.stem
                if module in modules:
                    raise RuntimeError(f"duplicate flattened GNU Gawk module: {module}")
                target = staged_sources / rust.name
                shutil.copy2(rust, target)
                declaration = rust.with_suffix(".c_decls.json")
                has_map = declaration.is_file()
                if has_map:
                    shutil.copy2(declaration, staged_sources / declaration.name)
                    declaration_maps += 1
                modules[module] = {"batch": batch.name, "sha256": sha256(target),
                                   "declaration_map": has_map}
        expected = (55, 53) if args.scope == "complete" else (37, 35)
        if (len(modules), declaration_maps) != expected:
            raise RuntimeError("combined GNU Gawk module coverage changed")
        missing = sorted(name for name, data in modules.items() if not data["declaration_map"])
        if missing != ["awkgram", "command"]:
            raise RuntimeError("GNU Gawk declaration-map exception set changed")
        declarations = "".join(
            f'#[path = "src/{name}.rs"]\npub mod {name};\n' for name in sorted(modules)
        )
        (staged / "lib.rs").write_text(PREAMBLE + declarations)
        package = "gawk_5_4_0_combined" if args.scope == "complete" else "gawk_5_4_0_core"
        (staged / "Cargo.toml").write_text(CARGO.format(package=package))
        (staged / "build.rs").write_text("fn main() {}\n")
        (staged / "rust-toolchain.toml").write_text(
            '[toolchain]\nchannel = "nightly-2023-04-15"\ncomponents = ["rustfmt"]\n'
        )
        (staged / "rustbox-combination.json").write_text(json.dumps({
            "schema": 1, "scope": args.scope, "batches": 7, "modules": len(modules),
            "declaration_maps": declaration_maps,
            "declaration_map_exceptions": missing, "module_inventory": modules,
        }, indent=2, sort_keys=True) + "\n")
        if output.exists():
            shutil.rmtree(output)
        staged.rename(output)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    print(json.dumps({"batches": 7, "declaration_maps": declaration_maps,
                      "modules": len(modules), "scope": args.scope}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
