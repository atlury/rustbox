#!/usr/bin/env python3
"""Stage Less 710 with deterministic multicall entrypoint normalization."""

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


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if text.count(old) != 1:
        raise RuntimeError(f"Less {label} precondition failed in {path}")
    path.write_text(text.replace(old, new))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    canonical = repository / "work/upstream/less-710"
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["less"]
    state = json.loads((repository / "work/upstream/.state/less.json").read_text())
    for key in ("version", "sha256", "signature_sha256", "signer_fingerprint"):
        if state.get(key) != release[key]:
            raise RuntimeError(f"Less source state changed at {key}")
    if not state.get("signature_verified"):
        raise RuntimeError("canonical Less signature state is incomplete")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    try:
        shutil.copytree(canonical, staged, symlinks=True)
        less_main = staged / "main.c"
        lessecho_main = staged / "lessecho.c"
        replace_once(
            less_main,
            "int main(int argc, constant char *argv[])\n{",
            "int rustbox_less_main(int argc, char **argv)\n{",
            "less multicall entrypoint",
        )
        less_main.write_text(less_main.read_text() + (
            "\n#ifndef RUSTBOX_MULTICALL\n"
            "int main(int argc, char **argv)\n"
            "{\n"
            "    return rustbox_less_main(argc, argv);\n"
            "}\n"
            "#endif\n"
        ))
        replace_once(
            lessecho_main,
            "int main(int argc, char *argv[])\n{",
            "int rustbox_lessecho_main(int argc, char **argv)\n{",
            "lessecho multicall entrypoint",
        )
        lessecho_main.write_text(lessecho_main.read_text() + (
            "\n#ifndef RUSTBOX_MULTICALL\n"
            "int main(int argc, char **argv)\n"
            "{\n"
            "    return rustbox_lessecho_main(argc, argv);\n"
            "}\n"
            "#endif\n"
        ))

        canonical_files = {
            path.relative_to(canonical).as_posix() for path in canonical.rglob("*") if path.is_file()
        }
        staged_files = {
            path.relative_to(staged).as_posix() for path in staged.rglob("*") if path.is_file()
        }
        if canonical_files != staged_files:
            raise RuntimeError("normalization added or removed Less source-tree files")
        changed = sorted(
            name for name in canonical_files if sha256(canonical / name) != sha256(staged / name)
        )
        if changed != ["lessecho.c", "main.c"]:
            raise RuntimeError(f"unexpected Less normalized sources: {changed}")
        operations = {
            "main.c": "export rustbox_less_main with char** ABI and retain a conditional standalone wrapper",
            "lessecho.c": "export rustbox_lessecho_main with char** ABI and retain a conditional standalone wrapper",
        }
        manifest = {
            "schema": 1,
            "release": release["version"],
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
                    "operation": operations[name],
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
