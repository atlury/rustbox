#!/usr/bin/env python3
"""Apply curl-specific stable-Rust ABI boundary decisions."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def retain_mprintf_c_boundary(crate: Path) -> dict[str, object]:
    library = crate / "lib.rs"
    module = crate / "src/lib/mprintf.rs"
    cargo = crate / "Cargo.toml"
    declaration = "pub mod mprintf;\n"
    text = library.read_text(encoding="utf-8")
    translated = module.read_text(encoding="utf-8")
    cargo_text = cargo.read_text(encoding="utf-8")
    if text.count(declaration) != 1:
        raise RuntimeError("curl mprintf module declaration is not unique")
    if translated.count("next_arg::<::f128::f128>()") != 1:
        raise RuntimeError("curl long-double va_arg boundary changed")
    if any(
        "::f128" in path.read_text(encoding="utf-8")
        for path in crate.rglob("*.rs")
        if path != module
    ):
        raise RuntimeError("curl gained another translated f128 boundary")
    imports = "extern crate f128;#[macro_use]\nextern crate num_traits;\n"
    if text.count(imports) != 1:
        raise RuntimeError("curl f128/num-traits import closure changed")
    dependencies = ("f128 = \"0.2\"\n", "num-traits = \"0.2\"\n")
    if any(cargo_text.count(dependency) != 1 for dependency in dependencies):
        raise RuntimeError("curl f128/num-traits dependency closure changed")

    library_before = sha256(library)
    cargo_before = sha256(cargo)
    library.write_text(
        text.replace(imports, "").replace(declaration, ""), encoding="utf-8"
    )
    for dependency in dependencies:
        cargo_text = cargo_text.replace(dependency, "")
    cargo.write_text(cargo_text, encoding="utf-8")
    return {
        "paths": [
            library.relative_to(crate).as_posix(),
            cargo.relative_to(crate).as_posix(),
        ],
        "before_sha256": [library_before, cargo_before],
        "after_sha256": [sha256(library), sha256(cargo)],
        "omitted_rust_module": "src/lib/mprintf.rs",
        "canonical_c_residue": "lib/mprintf.c",
        "removed_rust_dependencies": ["f128", "num-traits"],
        "operation": "retain canonical C for curl's variadic long-double formatter",
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
    if not (crate / "rustbox-modernization.json").is_file():
        raise RuntimeError("missing curl stable modernization manifest")

    manifest = {
        "schema": 1,
        "target": "x86_64-unknown-linux-gnu",
        "changes": [retain_mprintf_c_boundary(crate)],
    }
    output = crate / "rustbox-curl-stable.json"
    output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "canonical_c_sources": 1,
        "rust_sources": 239,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
