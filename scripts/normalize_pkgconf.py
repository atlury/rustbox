#!/usr/bin/env python3
"""Stage pkgconf with deterministic multicall entrypoint normalization."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path


ENTRYPOINTS = {
    "cli/main.c": "rustbox_pkgconf_main",
    "cli/bomtool/main.c": "rustbox_bomtool_main",
    "cli/pccritic/main.c": "rustbox_pccritic_main",
    "cli/spdxtool/main.c": "rustbox_spdxtool_main",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if relative.parts[0] == ".git":
            continue
        encoded = relative.as_posix().encode()
        if path.is_symlink():
            kind, payload = b"L", os.readlink(path).encode()
        elif path.is_file():
            kind, payload = b"F", path.read_bytes()
        elif path.is_dir():
            kind, payload = b"D", b""
        else:
            raise RuntimeError(f"unsupported source entry: {path}")
        digest.update(kind + b"\0" + encoded + b"\0" + payload + b"\0")
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    canonical = repository / "work/upstream/pkgconf-3.0.11"
    state = json.loads((repository / "work/upstream/.state/pkgconf.json").read_text())
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["pkgconf"]
    for key in ("version", "tag", "commit", "tree", "signer_fingerprint", "key_sha256"):
        if state.get(key) != release[key]:
            raise RuntimeError(f"pkgconf source state changed at {key}")
    if not state["signature_verified"]:
        raise RuntimeError("canonical pkgconf signed tag is not verified")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    changes: list[dict[str, str]] = []
    try:
        shutil.copytree(canonical, staged, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        for relative, exported in ENTRYPOINTS.items():
            target = staged / relative
            before = target.read_text()
            signature = "int\nmain(int argc, char *argv[])\n{"
            replacement = (
                f"int {exported}(int argc, char *argv[]);\n\n"
                f"int\n{exported}(int argc, char *argv[])\n{{"
            )
            if before.count(signature) != 1 or exported in before:
                raise RuntimeError(f"entrypoint normalization precondition failed: {relative}")
            wrapper = (
                "\n\n#ifndef RUSTBOX_MULTICALL\n"
                "int\nmain(int argc, char *argv[])\n{\n"
                f"\treturn {exported}(argc, argv);\n"
                "}\n#endif\n"
            )
            target.write_text(before.replace(signature, replacement) + wrapper)
            if target.read_text().count(exported) != 3:
                raise RuntimeError(f"entrypoint normalization postcondition failed: {relative}")
            changes.append(
                {
                    "source": relative,
                    "canonical_sha256": sha256(canonical / relative),
                    "normalized_sha256": sha256(target),
                    "operation": f"export {exported} with a conditional standalone main wrapper",
                }
            )

        sparse_source = "cli/spdxtool/core.c"
        sparse_target = staged / sparse_source
        before = sparse_target.read_text()
        old = "!creation->created_using | !creation->spec_version"
        new = "!creation->created_using || !creation->spec_version"
        if before.count(old) != 1:
            raise RuntimeError("Sparse boolean-or normalization precondition failed")
        sparse_target.write_text(before.replace(old, new))
        changes.append(
            {
                "source": sparse_source,
                "canonical_sha256": sha256(canonical / sparse_source),
                "normalized_sha256": sha256(sparse_target),
                "operation": "spell boolean disjunction with logical-or; operands are already evaluated pointer tests",
            }
        )

        changed = []
        for source in sorted(path for path in canonical.rglob("*") if path.is_file() and ".git" not in path.parts):
            relative = source.relative_to(canonical)
            if sha256(source) != sha256(staged / relative):
                changed.append(relative.as_posix())
        expected = sorted([*ENTRYPOINTS, sparse_source])
        if changed != expected:
            raise RuntimeError(f"unexpected normalized source changes: {changed}")

        manifest = {
            "schema": 1,
            "release": release["version"],
            "canonical_signed_tree": release["tree"],
            "canonical_tree_sha256": tree_digest(canonical),
            "normalized_tree_sha256": tree_digest(staged),
            "changed_sources": changed,
            "transformations": changes,
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
    print(json.dumps({"changed_sources": len(changed), "entrypoints": len(ENTRYPOINTS)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
