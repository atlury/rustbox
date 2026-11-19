#!/usr/bin/env python3
"""Mechanically make reachable C2Rust 0.22 output build on current stable Rust."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path


EXTERN_TYPE = re.compile(r"^\s*pub type ([A-Za-z_][A-Za-z0-9_]*);\s*$")
STATIC_MUT = re.compile(r"^\s*(?:pub\s+)?static\s+mut\s+([A-Za-z_][A-Za-z0-9_]*):")
TYPE_ALIAS = re.compile(
    r"^\s*pub\s+type\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*;\s*$"
)
REMOVED_FEATURES = {
    "#![feature(c_variadic)]",
    "#![feature(extern_types)]",
    "#![feature(label_break_value)]",
    "#![feature(raw_ref_op)]",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def has_only_pointer_uses(line: str, name: str) -> bool:
    """Accept every occurrence only when it denotes or constructs a raw pointer."""
    escaped = re.escape(name)
    # A C field and an opaque tag can legitimately share a spelling.  Remove
    # Rust field/argument labels before classifying occurrences in type position.
    residual = re.sub(rf"\b{escaped}\s*:", "", line)
    allowed = (
        rf"\*(?:mut|const)\s+{escaped}\b",
        rf"\bnull(?:_mut)?\s*::\s*<\s*{escaped}\s*>",
    )
    for pattern in allowed:
        residual = re.sub(pattern, "", residual)
    return re.search(rf"\b{escaped}\b", residual) is None


def transform_rust(path: Path) -> dict[str, object] | None:
    before = path.read_text(encoding="utf-8")
    lines = before.splitlines()
    opaque = [match.group(1) for line in lines if (match := EXTERN_TYPE.match(line))]
    kept = [line for line in lines if not EXTERN_TYPE.match(line) and line not in REMOVED_FEATURES]

    mutable_statics = {
        match.group(1) for line in kept if (match := STATIC_MUT.match(line))
    }
    raw_static_pointer_rewrites: list[str] = []
    for name in sorted(mutable_statics):
        pattern = re.compile(rf"&mut\s+{re.escape(name)}\s+as\s+\*mut\b")
        rewritten = []
        for line in kept:
            changed, count = pattern.subn(f"&raw mut {name} as *mut", line)
            if count:
                raw_static_pointer_rewrites.extend([name] * count)
            rewritten.append(changed)
        kept = rewritten

    for name in opaque:
        uses = [line for line in kept if re.search(rf"\b{re.escape(name)}\b", line)]
        for line in uses:
            alias = TYPE_ALIAS.match(line)
            if alias is not None and alias.group(2) == name:
                alias_name = alias.group(1)
                alias_uses = [
                    candidate for candidate in kept
                    if candidate != line
                    and re.search(rf"\b{re.escape(alias_name)}\b", candidate)
                ]
                if all(has_only_pointer_uses(candidate, alias_name) for candidate in alias_uses):
                    continue
            if not has_only_pointer_uses(line, name):
                raise RuntimeError(f"{path}: opaque type {name} has non-pointer use: {line}")

    definitions: list[str] = []
    for name in opaque:
        definitions.extend(
            [
                "#[repr(C)]",
                f"pub struct {name} {{",
                "    _private: [u8; 0],",
                "}",
            ]
        )
    after = "\n".join([*definitions, *kept]) + "\n"
    if after == before:
        return None
    path.write_text(after, encoding="utf-8")
    return {
        "path": str(path),
        "before_sha256": hashlib.sha256(before.encode()).hexdigest(),
        "after_sha256": hashlib.sha256(after.encode()).hexdigest(),
        "opaque_pointer_types": opaque,
        "raw_static_pointer_rewrites": raw_static_pointer_rewrites,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.input.resolve()
    output = args.output.resolve()
    if not (source / "Cargo.toml").is_file() or source == output:
        raise RuntimeError("input must be a C2Rust crate and output must differ")
    if output.parent != source.parent or not output.name.endswith("-stable") or output.is_symlink():
        raise RuntimeError("output must be a non-symlink *-stable sibling of input")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    try:
        shutil.copytree(
            source,
            staged,
            ignore=shutil.ignore_patterns("target", "Cargo.lock"),
        )
        changes: list[dict[str, object]] = []
        for path in sorted(staged.rglob("*.rs")):
            change = transform_rust(path)
            if change is not None:
                change["path"] = str(path.relative_to(staged))
                changes.append(change)
        (staged / "rust-toolchain.toml").write_text(
            '[toolchain]\nchannel = "1.99.0"\nprofile = "minimal"\n', encoding="utf-8"
        )
        if any("#![feature(" in path.read_text(encoding="utf-8") for path in staged.rglob("*.rs")):
            raise RuntimeError("stable output still contains a feature gate")
        manifest = {
            "schema": 1,
            "input_cargo_sha256": digest(source / "Cargo.toml"),
            "stable_toolchain": "1.99.0",
            "changes": changes,
        }
        (staged / "rustbox-modernization.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if output.exists():
            shutil.rmtree(output)
        staged.rename(output)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
