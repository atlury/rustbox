#!/usr/bin/env python3
"""Prepare a sibling C2Rust crate by repairing only generated build metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path


NUM_TRAITS_IMPORT = re.compile(r"^\s*use\s+::num_traits::", re.MULTILINE)
VA_LIST_USE = re.compile(r"::core::ffi::VaList\b")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def add_dependency(manifest: str, crate: str, requirement: str) -> str:
    lines = manifest.splitlines()
    try:
        section = lines.index("[dependencies]")
    except ValueError as error:
        raise RuntimeError("C2Rust manifest has no [dependencies] section") from error
    end = next(
        (index for index in range(section + 1, len(lines)) if lines[index].startswith("[")),
        len(lines),
    )
    dependency = re.compile(rf"^\s*{re.escape(crate)}\s*=")
    if any(dependency.match(line) for line in lines[section + 1 : end]):
        return manifest
    entries = [line for line in lines[section + 1 : end] if line.strip()]
    entries.append(f'{crate} = "{requirement}"')
    entries.sort(key=lambda line: line.split("=", 1)[0].strip())
    lines[section + 1 : end] = entries
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.input.resolve()
    output = args.output.resolve()
    if not (source / "Cargo.toml").is_file() or source == output:
        raise RuntimeError("input must be a C2Rust crate and output must differ")
    if output.parent != source.parent or not output.name.endswith("-prepared") or output.is_symlink():
        raise RuntimeError("output must be a non-symlink *-prepared sibling of input")

    rust_text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(source.rglob("*.rs"))
    )
    before = (source / "Cargo.toml").read_text(encoding="utf-8")
    after = before
    additions: list[dict[str, str]] = []
    if NUM_TRAITS_IMPORT.search(rust_text):
        changed = add_dependency(after, "num-traits", "0.2")
        if changed != after:
            additions.append({
                "crate": "num-traits",
                "requirement": "0.2",
                "reason": "generated Rust directly imports num_traits::Float",
            })
        after = changed

    feature_additions: list[str] = []
    lib_before = (source / "lib.rs").read_text(encoding="utf-8")
    lib_after = lib_before
    if VA_LIST_USE.search(rust_text) and "#![feature(c_variadic)]" not in lib_before:
        feature_lines = list(re.finditer(r"^#!\[feature\([^\n]+\)\]\n", lib_before, re.MULTILINE))
        if not feature_lines:
            raise RuntimeError("generated crate has no feature insertion point")
        insertion = feature_lines[-1].end()
        lib_after = lib_before[:insertion] + "#![feature(c_variadic)]\n" + lib_before[insertion:]
        feature_additions.append("c_variadic")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    try:
        shutil.copytree(
            source,
            staged,
            ignore=shutil.ignore_patterns(
                "target", "Cargo.lock", "rustbox-cargo-check.json"
            ),
        )
        (staged / "Cargo.toml").write_text(after, encoding="utf-8")
        (staged / "lib.rs").write_text(lib_after, encoding="utf-8")
        record = {
            "schema": 1,
            "input_cargo_sha256": hashlib.sha256(before.encode()).hexdigest(),
            "output_cargo_sha256": hashlib.sha256(after.encode()).hexdigest(),
            "dependency_additions": additions,
            "crate_feature_additions": feature_additions,
            "rust_files_changed": int(lib_after != lib_before),
        }
        (staged / "rustbox-scaffold.json").write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if output.exists():
            shutil.rmtree(output)
        staged.rename(output)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    print(json.dumps(record, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
