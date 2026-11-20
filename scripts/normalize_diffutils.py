#!/usr/bin/env python3
"""Stage GNU Diffutils with deterministic multicall entrypoint normalization."""

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


def normalize_entrypoint(path: Path, name: str, signature: str) -> None:
    before = path.read_text()
    export = f"rustbox_{name}_main"
    if before.count(signature) != 1 or export in before:
        raise RuntimeError(f"GNU Diffutils {name} entrypoint precondition failed")
    arguments = "char *argv[]" if name == "sdiff" else "char **argv"
    replacement = (
        f"int {export} (int argc, {arguments});\n\n"
        "int\n"
        f"{export} (int argc, {arguments})\n"
        "{"
    )
    wrapper = (
        "\n#ifndef RUSTBOX_MULTICALL\n"
        "int\n"
        f"main (int argc, {arguments})\n"
        "{\n"
        f"  return {export} (argc, argv);\n"
        "}\n"
        "#endif\n"
    )
    path.write_text(before.replace(signature, replacement) + wrapper)
    if path.read_text().count(export) != 3:
        raise RuntimeError(f"GNU Diffutils {name} entrypoint postcondition failed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    canonical = repository / "work/upstream/diffutils-3.12"
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["diffutils"]
    state = json.loads((repository / "work/upstream/.state/diffutils.json").read_text())
    for key in ("version", "sha256", "signature_sha256", "signer_fingerprint", "key_sha256"):
        if state.get(key) != release[key]:
            raise RuntimeError(f"GNU Diffutils source state changed at {key}")
    if not state["signature_verified"]:
        raise RuntimeError("canonical GNU Diffutils release signature is not verified")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    try:
        shutil.copytree(canonical, staged, symlinks=True)
        normalize_entrypoint(staged / "src/cmp.c", "cmp", "int\nmain (int argc, char **argv)\n{")
        normalize_entrypoint(staged / "src/diff.c", "diff", "int\nmain (int argc, char **argv)\n{")
        normalize_entrypoint(staged / "src/diff3.c", "diff3", "int\nmain (int argc, char **argv)\n{")
        normalize_entrypoint(staged / "src/sdiff.c", "sdiff", "int\nmain (int argc, char *argv[])\n{")

        canonical_files = {
            path.relative_to(canonical).as_posix()
            for path in canonical.rglob("*") if path.is_file()
        }
        staged_files = {
            path.relative_to(staged).as_posix()
            for path in staged.rglob("*") if path.is_file()
        }
        if canonical_files != staged_files:
            raise RuntimeError("normalization added or removed GNU Diffutils source-tree files")
        changed = sorted(
            name for name in canonical_files
            if sha256(canonical / name) != sha256(staged / name)
        )
        expected_changed = ["src/cmp.c", "src/diff.c", "src/diff3.c", "src/sdiff.c"]
        if changed != expected_changed:
            raise RuntimeError(f"unexpected GNU Diffutils normalized sources: {changed}")

        transformations = [
            {
                "source": name,
                "canonical_sha256": sha256(canonical / name),
                "normalized_sha256": sha256(staged / name),
                "operation": f"export rustbox_{Path(name).stem}_main with a conditional standalone main wrapper",
                "engine": "exact deterministic source rewrite",
            }
            for name in changed
        ]
        manifest = {
            "schema": 1,
            "release": release["version"],
            "canonical_archive_sha256": release["sha256"],
            "canonical_tree_sha256": tree_digest(canonical),
            "normalized_tree_sha256": tree_digest(staged),
            "changed_sources": changed,
            "transformations": transformations,
            "entrypoints": ["rustbox_cmp_main", "rustbox_diff_main", "rustbox_diff3_main", "rustbox_sdiff_main"],
            "conditional": "RUSTBOX_MULTICALL",
            "engine": "exact deterministic source rewrite",
        }
        if output.exists():
            shutil.rmtree(output)
        staged.rename(output)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"changed_sources": 4, "entrypoints": 4}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
