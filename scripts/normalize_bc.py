#!/usr/bin/env python3
"""Stage GNU bc with deterministic multicall-entrypoint normalization."""

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


def export_entrypoint(path: Path, signature: str, replacement: str, name: str) -> None:
    before = path.read_text()
    if before.count(signature) != 1 or name in before:
        raise RuntimeError(f"GNU bc entrypoint precondition failed in {path}")
    wrapper = (
        "\n#ifndef RUSTBOX_MULTICALL\n"
        "int\n"
        "main (int argc, char **argv)\n"
        "{\n"
        f"  return {name} (argc, argv);\n"
        "}\n"
        "#endif\n"
    )
    path.write_text(before.replace(signature, replacement) + wrapper)
    if path.read_text().count(name) != 2:
        raise RuntimeError(f"GNU bc entrypoint postcondition failed in {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    canonical = repository / "work/upstream/bc-1.08.2"
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["bc"]
    state = json.loads((repository / "work/upstream/.state/bc.json").read_text())
    for key in ("version", "sha256", "signature_sha256", "signer_fingerprint", "key_sha256"):
        if state.get(key) != release[key]:
            raise RuntimeError(f"GNU bc source state changed at {key}")
    if not state["signature_verified"]:
        raise RuntimeError("canonical GNU bc release signature is not verified")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    try:
        shutil.copytree(canonical, staged, symlinks=True)
        export_entrypoint(
            staged / "bc/main.c",
            "int\nmain (int argc, char **argv)\n{",
            "int\nrustbox_bc_main (int argc, char **argv)\n{",
            "rustbox_bc_main",
        )
        export_entrypoint(
            staged / "dc/dc.c",
            "int\nmain(int argc, char **argv)\n{",
            "int\nrustbox_dc_main(int argc, char **argv)\n{",
            "rustbox_dc_main",
        )

        canonical_files = {
            path.relative_to(canonical).as_posix()
            for path in canonical.rglob("*") if path.is_file()
        }
        staged_files = {
            path.relative_to(staged).as_posix()
            for path in staged.rglob("*") if path.is_file()
        }
        if canonical_files != staged_files:
            raise RuntimeError("normalization added or removed GNU bc source-tree files")
        changed = sorted(
            name for name in canonical_files
            if sha256(canonical / name) != sha256(staged / name)
        )
        if changed != ["bc/main.c", "dc/dc.c"]:
            raise RuntimeError(f"unexpected GNU bc normalized sources: {changed}")

        manifest = {
            "schema": 1,
            "release": release["version"],
            "bundled_dc_release": "1.5.2",
            "canonical_archive_sha256": release["sha256"],
            "canonical_tree_sha256": tree_digest(canonical),
            "normalized_tree_sha256": tree_digest(staged),
            "changed_sources": changed,
            "conditional": "RUSTBOX_MULTICALL",
            "engine": "exact deterministic source rewrite",
            "transformations": [
                {
                    "source": name,
                    "canonical_sha256": sha256(canonical / name),
                    "normalized_sha256": sha256(staged / name),
                    "operation": "export a Rustbox multicall entrypoint while retaining a conditional standalone main wrapper",
                }
                for name in changed
            ],
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
