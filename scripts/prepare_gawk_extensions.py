#!/usr/bin/env python3
"""Create one raw C2Rust crate per canonical GNU Gawk extension."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path


EXTENSIONS = {
    "filefuncs": ("filefuncs", "stack", "gawkfts"),
    "fnmatch": ("fnmatch",),
    "fork": ("fork",),
    "inplace": ("inplace",),
    "intdiv": ("intdiv",),
    "ordchr": ("ordchr",),
    "readdir": ("readdir",),
    "readfile": ("readfile",),
    "revoutput": ("revoutput",),
    "revtwoway": ("revtwoway",),
    "rwarray": ("rwarray",),
    "testext": ("testext",),
    "time": ("time",),
}

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

CARGO = """[package]
name = "gawk_ext_{name}"
version = "0.0.0"
publish = false
edition = "2021"
autobins = false

[lib]
name = "{name}"
path = "lib.rs"
crate-type = ["cdylib"]

[dependencies]
c2rust-bitfields = "0.22.1"
f128 = "0.2"
libc = "0.2"
num-traits = "0.2"
"""


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, output = args.input.resolve(), args.output.resolve()
    modules = {path.stem: path for path in source.glob("batch-*/src/extension/*.rs")}
    expected = sorted({module for closure in EXTENSIONS.values() for module in closure})
    if sorted(modules) != expected or len(modules) != 15:
        raise RuntimeError("GNU Gawk translated extension surface changed")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    staged.mkdir()
    try:
        for name, closure in EXTENSIONS.items():
            crate = staged / name
            sources = crate / "src"
            sources.mkdir(parents=True)
            for module in closure:
                shutil.copy2(modules[module], sources / f"{module}.rs")
            declarations = "".join(
                f'#[path = "src/{module}.rs"]\npub mod {module};\n' for module in closure
            )
            (crate / "lib.rs").write_text(PREAMBLE + declarations)
            (crate / "Cargo.toml").write_text(CARGO.format(name=name))
            libraries = ["m"]
            if name in {"intdiv", "rwarray", "testext"}:
                libraries[0:0] = ["mpfr", "gmp"]
            (crate / "build.rs").write_text("fn main() {\n" + "".join(
                f'    println!("cargo:rustc-link-lib={library}");\n'
                for library in libraries
            ) + "}\n")
            (crate / "rust-toolchain.toml").write_text(
                '[toolchain]\nchannel = "nightly-2023-04-15"\ncomponents = ["rustfmt"]\n'
            )
        (staged / "rustbox-extensions.json").write_text(json.dumps({
            "schema": 1,
            "extensions": {name: list(closure) for name, closure in EXTENSIONS.items()},
            "libraries": len(EXTENSIONS),
            "modules": len(modules),
        }, indent=2, sort_keys=True) + "\n")
        if output.exists():
            shutil.rmtree(output)
        staged.rename(output)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    print(json.dumps({"libraries": len(EXTENSIONS), "modules": len(modules)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
