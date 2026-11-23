#!/usr/bin/env python3
"""Apply Kmod-specific stable-Rust representation repairs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--crate", required=True, type=Path)
    args = parser.parse_args()
    crate = args.crate.resolve()
    modernization = crate / "rustbox-modernization.json"
    if not modernization.is_file():
        raise RuntimeError("missing Kmod stable modernization manifest")

    module = crate / "src/libkmod/libkmod_module.rs"
    text = module.read_text(encoding="utf-8")
    before = digest(module)
    replacements = [
        ("((true_0 != 0) != 0)", "(true_0 != 0)", 10),
        ("((false_0 != 0) != 0)", "(false_0 != 0)", 1),
        (
            "((!pre.is_null() || !post.is_null()) != 0)",
            "(!pre.is_null() || !post.is_null())",
            1,
        ),
    ]
    changes = []
    for old, new, expected in replacements:
        count = text.count(old)
        if count != expected:
            raise RuntimeError(
                f"Kmod generated-bitfield boolean shape changed: {old!r}: "
                f"expected {expected}, found {count}"
            )
        text = text.replace(old, new)
        changes.append({"from": old, "to": new, "occurrences": count})
    module.write_text(text, encoding="utf-8")

    manifest = {
        "schema": 1,
        "path": str(module.relative_to(crate)),
        "before_sha256": before,
        "after_sha256": digest(module),
        "operation": "remove redundant integer comparison from bool bitfield setters",
        "semantic_basis": (
            "the C2Rust bitfield setters accept Rust bool; their arguments were "
            "already boolean expressions before C2Rust's invalid bool-to-bool cast"
        ),
        "changes": changes,
        "stable_representation_repairs": sum(item[2] for item in replacements),
    }
    output = crate / "rustbox-kmod-stable.json"
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "canonical_c_sources": 0,
        "rust_sources": len(list(crate.rglob("*.rs"))),
        "stable_representation_repairs": manifest["stable_representation_repairs"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
