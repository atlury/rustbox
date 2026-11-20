#!/usr/bin/env python3
"""Stage GNU M4 with a deterministic multicall entrypoint normalization."""

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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    canonical = repository / "work/upstream/m4-1.4.21"
    state = json.loads((repository / "work/upstream/.state/m4.json").read_text())
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["m4"]
    if not state["signature_verified"] or state["sha256"] != release["sha256"]:
        raise RuntimeError("canonical M4 source is not signature-verified")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    try:
        shutil.copytree(canonical, staged, symlinks=True)
        target = staged / "src/m4.c"
        before = target.read_text()
        signature = "int\nmain (int argc, char *const *argv)\n{"
        replacement = "int\nrustbox_m4_main (int argc, char *const *argv)\n{"
        if before.count(signature) != 1 or "rustbox_m4_main" in before:
            raise RuntimeError("M4 entrypoint normalization precondition failed")
        wrapper = """

#ifndef RUSTBOX_MULTICALL
int
main (int argc, char *const *argv)
{
  return rustbox_m4_main (argc, argv);
}
#endif
"""
        target.write_text(before.replace(signature, replacement) + wrapper)
        if target.read_text().count("rustbox_m4_main") != 2:
            raise RuntimeError("M4 entrypoint normalization postcondition failed")

        changed = []
        for source in sorted(path for path in canonical.rglob("*") if path.is_file()):
            relative = source.relative_to(canonical)
            if sha256(source) != sha256(staged / relative):
                changed.append(relative.as_posix())
        if changed != ["src/m4.c"]:
            raise RuntimeError(f"unexpected normalized source changes: {changed}")

        manifest = {
            "schema": 1,
            "release": release["version"],
            "canonical_archive_sha256": release["sha256"],
            "canonical_tree_sha256": tree_digest(canonical),
            "normalized_tree_sha256": tree_digest(staged),
            "changed_sources": changed,
            "transformation": {
                "engine": "exact",
                "source": "src/m4.c",
                "canonical_sha256": sha256(canonical / "src/m4.c"),
                "normalized_sha256": sha256(target),
                "purpose": "Export rustbox_m4_main while retaining a conditional standalone main wrapper.",
            },
        }
        if output.exists():
            shutil.rmtree(output)
        staged.rename(output)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"changed_sources": changed, "release": release["version"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
