#!/usr/bin/env python3
"""Stage Flex with a deterministic multicall entrypoint transformation."""

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
    canonical = repository / "work/upstream/flex-2.6.4"
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["flex"]
    state = json.loads((repository / "work/upstream/.state/flex.json").read_text())
    for key in ("version", "sha256", "signature_sha256", "signer_fingerprint", "key_sha256"):
        if state.get(key) != release[key]:
            raise RuntimeError(f"Flex source state changed at {key}")
    if not state["signature_verified"]:
        raise RuntimeError("canonical Flex signature state is incomplete")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    try:
        shutil.copytree(canonical, staged, symlinks=True)
        main_c = staged / "src/main.c"
        text = main_c.read_text()
        signature = "int main (int argc, char *argv[])\n{"
        if text.count(signature) != 1:
            raise RuntimeError("Flex standalone-main precondition failed")
        text = text.replace(
            signature,
            "int rustbox_flex_main (int argc, char *argv[])\n{",
        )
        cleanup_sites = (
            (
                "\t\t\t\t program_name);\n\t\t\tFLEX_EXIT (1);",
                "\t\t\t\t program_name);\n\t\t\tscanopt_destroy (sopt);\n"
                "\t\t\tFLEX_EXIT (1);",
            ),
            (
                "\t\tcase OPT_HELP:\n\t\t\tusage ();\n\t\t\tFLEX_EXIT (0);",
                "\t\tcase OPT_HELP:\n\t\t\tusage ();\n"
                "\t\t\tscanopt_destroy (sopt);\n\t\t\tFLEX_EXIT (0);",
            ),
            (
                "\t\tcase OPT_VERSION:\n"
                "\t\t\tprintf (_(\"%s %s\\n\"), program_name, flex_version);\n"
                "\t\t\tFLEX_EXIT (0);",
                "\t\tcase OPT_VERSION:\n"
                "\t\t\tprintf (_(\"%s %s\\n\"), program_name, flex_version);\n"
                "\t\t\tscanopt_destroy (sopt);\n\t\t\tFLEX_EXIT (0);",
            ),
        )
        for old, new in cleanup_sites:
            if text.count(old) != 1:
                raise RuntimeError("Flex scanopt-cleanup precondition failed")
            text = text.replace(old, new)
        text += (
            "\n#ifndef RUSTBOX_MULTICALL\n"
            "int main (int argc, char *argv[])\n"
            "{\n"
            "\treturn rustbox_flex_main (argc, argv);\n"
            "}\n"
            "#endif\n"
        )
        main_c.write_text(text)

        canonical_files = {
            path.relative_to(canonical).as_posix()
            for path in canonical.rglob("*") if path.is_file()
        }
        staged_files = {
            path.relative_to(staged).as_posix()
            for path in staged.rglob("*") if path.is_file()
        }
        if canonical_files != staged_files:
            raise RuntimeError("normalization changed the Flex file set")
        changed = sorted(
            name for name in canonical_files
            if sha256(canonical / name) != sha256(staged / name)
        )
        if changed != ["src/main.c"]:
            raise RuntimeError(f"unexpected normalized Flex sources: {changed}")

        manifest = {
            "schema": 1,
            "release": "2.6.4",
            "canonical_archive_sha256": release["sha256"],
            "canonical_tree_sha256": tree_digest(canonical),
            "normalized_tree_sha256": tree_digest(staged),
            "changed_sources": changed,
            "entrypoint": "rustbox_flex_main",
            "conditional": "RUSTBOX_MULTICALL",
            "engine": "exact deterministic source rewrite",
            "transformations": [{
                "source": "src/main.c",
                "canonical_sha256": sha256(canonical / "src/main.c"),
                "normalized_sha256": sha256(staged / "src/main.c"),
                "operation": (
                    "rename only the locale-initializing standalone wrapper to "
                    "rustbox_flex_main and retain a conditional main wrapper"
                ),
            }, {
                "source": "src/main.c",
                "canonical_sha256": sha256(canonical / "src/main.c"),
                "normalized_sha256": sha256(staged / "src/main.c"),
                "operation": (
                    "destroy the initialized scanopt object before the three "
                    "option-parser exits that bypass the canonical cleanup"
                ),
                "semantic_basis": (
                    "scanopt_destroy frees only scanopt-owned option metadata "
                    "after the final diagnostic or output byte has been emitted"
                ),
            }],
        }
        if output.exists():
            shutil.rmtree(output)
        staged.rename(output)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"changed_sources": changed, "entrypoint": "rustbox_flex_main"},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
