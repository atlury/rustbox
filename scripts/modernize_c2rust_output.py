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
RUST_LITERAL = re.compile(
    r"(?:b|c)?r\#*\".*?\"\#*|(?:b|c)?\"(?:\\.|[^\"\\])*\"|b?'(?:\\.|[^'\\])*'"
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
    # A spelling inside a byte/string/character literal or trailing comment is
    # data, not a Rust identifier use.  C2Rust commonly emits option names that
    # happen to match opaque C tags (for example b"exclude\\0").
    residual = RUST_LITERAL.sub("", line)
    residual = "\n".join(line.split("//", 1)[0] for line in residual.splitlines())
    # A C field and an opaque tag can legitimately share a spelling.  Remove
    # Rust field/argument labels before classifying occurrences in type position.
    residual = re.sub(rf"\b{escaped}\s*:", "", residual)
    allowed = (
        rf"\*(?:mut|const)\s+{escaped}\b",
        rf"\bnull(?:_mut)?\s*::\s*<\s*{escaped}\s*,?\s*>",
    )
    for pattern in allowed:
        residual = re.sub(pattern, "", residual)
    return re.search(rf"\b{escaped}\b", residual) is None


def alias_has_only_pointer_uses(
    lines: list[str], name: str, visited: frozenset[str] = frozenset()
) -> bool:
    """Accept an opaque alias chain only when every leaf use is a pointer use."""
    if name in visited:
        return False
    descendants = visited | {name}
    for line in lines:
        if not re.search(rf"\b{re.escape(name)}\b", line):
            continue
        alias = TYPE_ALIAS.match(line)
        if alias is not None and alias.group(1) == name:
            continue
        if alias is not None and alias.group(2) == name:
            if not alias_has_only_pointer_uses(lines, alias.group(1), descendants):
                return False
            continue
        if not has_only_pointer_uses(line, name):
            return False
    return True


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
        mutable_pattern = re.compile(rf"&mut\s+{re.escape(name)}\s+as\s+\*mut\b")
        const_pattern = re.compile(rf"&\s*{re.escape(name)}\s+as\s+\*const\b")
        rewritten = []
        for line in kept:
            changed, mutable_count = mutable_pattern.subn(
                f"&raw mut {name} as *mut", line
            )
            changed, const_count = const_pattern.subn(
                f"&raw const {name} as *const", changed
            )
            if mutable_count or const_count:
                raw_static_pointer_rewrites.extend(
                    [name] * (mutable_count + const_count)
                )
            rewritten.append(changed)
        kept = rewritten

    for name in opaque:
        uses = [
            (index, line)
            for index, line in enumerate(kept)
            if re.search(rf"\b{re.escape(name)}\b", line)
        ]
        for index, line in uses:
            alias = TYPE_ALIAS.match(line)
            if alias is not None and alias.group(2) == name:
                if alias_has_only_pointer_uses(kept, alias.group(1)):
                    continue
            if not has_only_pointer_uses(line, name):
                context = "\n".join(kept[max(0, index - 2):index + 3])
                if not has_only_pointer_uses(context, name):
                    raise RuntimeError(f"{path}: opaque type {name} has non-pointer use: {line}")

    # C variadics are stable now, but C2Rust 0.22 emitted the old internal
    # VaListImpl spelling and borrowed it through as_va_list().  The stable
    # public type is VaList itself; clone() is its stable va_copy operation and
    # supplies an independently owned cursor to each by-value C ABI call.  Rust
    # 1.99 renamed the cursor-reading method from arg() to next_arg().
    va_list_impl_rewrites = sum(line.count("::core::ffi::VaListImpl") for line in kept)
    as_va_list_rewrites = sum(line.count(".as_va_list()") for line in kept)
    va_arg_rewrites = sum(line.count(".arg::<") for line in kept)
    kept = [
        line.replace("::core::ffi::VaListImpl", "::core::ffi::VaList")
        .replace(".as_va_list()", ".clone()")
        .replace(".arg::<", ".next_arg::<")
        for line in kept
    ]

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
        "va_list_impl_rewrites": va_list_impl_rewrites,
        "as_va_list_rewrites": as_va_list_rewrites,
        "va_arg_rewrites": va_arg_rewrites,
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
