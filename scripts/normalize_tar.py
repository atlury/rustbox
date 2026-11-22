#!/usr/bin/env python3
"""Stage GNU tar with deterministic, translation-friendly C normalization."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix().encode()
        if path.is_symlink():
            kind, payload = b"L", os.readlink(path).encode()
        elif path.is_file():
            kind, payload = b"F", path.read_bytes()
        elif path.is_dir():
            kind, payload = b"D", b""
        else:
            raise RuntimeError(f"unsupported source entry: {path}")
        digest.update(kind + b"\0" + relative + b"\0" + payload + b"\0")
    return digest.hexdigest()


def export_entrypoint(path: Path, exported: str) -> None:
    text = path.read_text()
    old = "int\nmain (int argc, char **argv)\n{"
    new = f"int\n{exported} (int argc, char **argv)\n{{"
    if text.count(old) != 1:
        raise RuntimeError(f"GNU tar entrypoint precondition failed: {path}")
    text = text.replace(old, new)
    text += (
        "\n#ifndef RUSTBOX_MULTICALL\n"
        "int\nmain (int argc, char **argv)\n"
        "{\n"
        f"  return {exported} (argc, argv);\n"
        "}\n"
        "#endif\n"
    )
    path.write_text(text)


def normalize_long_double_uintmax(path: Path) -> dict[str, str]:
    """Spell one same-range cast in a form C2Rust can represent on LP64."""
    text = path.read_text()
    include_before = "#include <locale.h>\n"
    include_after = "#include <limits.h>\n#include <locale.h>\n"
    cast_before = "      uintmax_t u = value;\n"
    cast_after = (
        "#if UINTMAX_MAX == ULONG_MAX\n"
        "      unsigned long u = value;\n"
        "#else\n"
        "      uintmax_t u = value;\n"
        "#endif\n"
    )
    if text.count(include_before) != 1 or text.count(cast_before) != 1:
        raise RuntimeError(f"GNU tar human-number precondition failed: {path}")
    text = text.replace(include_before, include_after)
    text = text.replace(cast_before, cast_after)
    path.write_text(text)
    return {
        "source": "gnu/human.c",
        "operation": (
            "on targets where uintmax_t and unsigned long have the same range, "
            "make the existing long-double conversion's unsigned-long type explicit"
        ),
        "semantic_basis": (
            "UINTMAX_MAX == ULONG_MAX proves the selected conversion has the same "
            "range and C conversion semantics; other targets retain the canonical cast"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    repository = args.repository.resolve()
    canonical = repository / "work/upstream/tar-1.35"
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["tar"]
    state = json.loads((repository / "work/upstream/.state/tar.json").read_text())
    for key in (
        "version", "sha256", "signature_sha256", "signer_fingerprint", "key_sha256"
    ):
        if state.get(key) != release[key]:
            raise RuntimeError(f"GNU tar source state changed at {key}")
    if not state["signature_verified"]:
        raise RuntimeError("canonical GNU tar signature state is incomplete")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    changed: list[str] = []
    try:
        shutil.copytree(canonical, staged, symlinks=True)
        transformations = []
        for relative, exported in (
            ("src/tar.c", "rustbox_tar_main"),
            ("rmt/rmt.c", "rustbox_rmt_main"),
        ):
            path = staged / relative
            canonical_digest = sha256(canonical / relative)
            export_entrypoint(path, exported)
            transformations.append({
                "source": relative,
                "canonical_sha256": canonical_digest,
                "normalized_sha256": sha256(path),
                "operation": f"export {exported} and retain a conditional standalone main wrapper",
            })

        human = staged / "gnu/human.c"
        canonical_digest = sha256(canonical / "gnu/human.c")
        transformation = normalize_long_double_uintmax(human)
        transformation.update({
            "canonical_sha256": canonical_digest,
            "normalized_sha256": sha256(human),
        })
        transformations.append(transformation)

        canonical_files = {
            path.relative_to(canonical).as_posix()
            for path in canonical.rglob("*") if path.is_file()
        }
        staged_files = {
            path.relative_to(staged).as_posix()
            for path in staged.rglob("*") if path.is_file()
        }
        if canonical_files != staged_files:
            raise RuntimeError("normalization added or removed GNU tar source-tree files")
        changed = sorted(
            name for name in canonical_files
            if sha256(canonical / name) != sha256(staged / name)
        )
        if changed != ["gnu/human.c", "rmt/rmt.c", "src/tar.c"]:
            raise RuntimeError(f"unexpected GNU tar normalized sources: {changed}")

        manifest = {
            "schema": 1,
            "release": release["version"],
            "canonical_archive_sha256": release["sha256"],
            "canonical_tree_sha256": tree_digest(canonical),
            "normalized_tree_sha256": tree_digest(staged),
            "changed_sources": changed,
            "entrypoints": 2,
            "conditional": "RUSTBOX_MULTICALL",
            "engine": "exact deterministic source rewrite",
            "transformations": transformations,
        }
        if output.exists():
            shutil.rmtree(output)
        staged.rename(output)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"changed_sources": changed, "entrypoints": 2}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
