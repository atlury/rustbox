#!/usr/bin/env python3
"""Link C2Rust opaque declarations to unique concrete translated structs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path


STRUCT = re.compile(r"^pub struct ([A-Za-z_][A-Za-z0-9_]*)\s*\{", re.MULTILINE)
OPAQUE_LINE = re.compile(r"^(?P<indent>\s*)pub type (?P<name>[A-Za-z_][A-Za-z0-9_]*);\s*$", re.MULTILINE)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module_path(root: Path, path: Path) -> str:
    relative = path.relative_to(root).with_suffix("")
    return "crate::" + "::".join(relative.parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.input.resolve()
    output = args.output.resolve()
    if not (source / "Cargo.toml").is_file() or source == output:
        raise RuntimeError("input must be a C2Rust crate and output must differ")
    if output.parent != source.parent or not output.name.endswith("-linked") or output.is_symlink():
        raise RuntimeError("output must be a non-symlink *-linked sibling of input")

    definitions: dict[str, list[Path]] = defaultdict(list)
    for path in sorted(source.rglob("*.rs")):
        for match in STRUCT.finditer(path.read_text(encoding="utf-8")):
            definitions[match.group(1)].append(path)
    unique = {name: paths[0] for name, paths in definitions.items() if len(paths) == 1}

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    changes: list[dict[str, object]] = []
    try:
        shutil.copytree(source, staged, ignore=shutil.ignore_patterns("target", "Cargo.lock"))
        for path in sorted(staged.rglob("*.rs")):
            before = path.read_text(encoding="utf-8")
            imports: dict[str, str] = {}

            def replace(match: re.Match[str]) -> str:
                name = match.group("name")
                canonical_source = unique.get(name)
                if canonical_source is None:
                    return match.group(0)
                canonical = staged / canonical_source.relative_to(source)
                if canonical == path:
                    return match.group(0)
                imports[name] = f"use {module_path(staged, canonical)}::{name};"
                return ""

            body = OPAQUE_LINE.sub(replace, before)
            if not imports:
                continue
            insertion = "\n".join(imports[name] for name in sorted(imports)) + "\n"
            body = insertion + body
            path.write_text(body, encoding="utf-8")
            changes.append({
                "path": path.relative_to(staged).as_posix(),
                "before_sha256": hashlib.sha256(before.encode()).hexdigest(),
                "after_sha256": hashlib.sha256(body.encode()).hexdigest(),
                "linked_types": {
                    name: unique[name].relative_to(source).as_posix()
                    for name in sorted(imports)
                },
            })

        linked = sorted({name for change in changes for name in change["linked_types"]})
        expected = sorted(name for name in unique if any(
            re.search(rf"^\s*pub type {re.escape(name)};\s*$", path.read_text(), re.MULTILINE)
            for path in source.rglob("*.rs")
        ))
        if linked != expected:
            raise RuntimeError(f"cross-module type closure changed: {linked} != {expected}")
        manifest = {
            "schema": 1,
            "input_cargo_sha256": sha256(source / "Cargo.toml"),
            "linked_types": linked,
            "changed_files": len(changes),
            "changes": changes,
        }
        (staged / "rustbox-cross-module-types.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        if output.exists():
            shutil.rmtree(output)
        staged.rename(output)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    print(json.dumps({
        "changed_files": len(changes), "linked_types": linked,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
