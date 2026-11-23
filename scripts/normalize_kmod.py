#!/usr/bin/env python3
"""Stage Kmod with a deterministic reentrant multicall entrypoint."""

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
    canonical = repository / "work/upstream/kmod-34.3"
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["kmod"]
    state = json.loads((repository / "work/upstream/.state/kmod.json").read_text())
    for key in ("version", "sha256", "signature_sha256", "signer_fingerprint", "key_sha256"):
        if state.get(key) != release[key]:
            raise RuntimeError(f"Kmod source state changed at {key}")
    if state.get("signature_verified") is not True:
        raise RuntimeError("canonical Kmod signature state is incomplete")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    try:
        shutil.copytree(canonical, staged, symlinks=True)
        main_c = staged / "tools/kmod.c"
        text = main_c.read_text()
        signature = "int main(int argc, char *argv[])\n{\n\tint err;"
        replacement = (
            "int rustbox_kmod_main(int argc, char *argv[])\n"
            "{\n"
            "\tint err;\n"
            "\tchar *slash;\n\n"
            "\tif (argc > 0 && argv[0] != NULL) {\n"
            "\t\tprogram_invocation_name = argv[0];\n"
            "\t\tslash = strrchr(argv[0], '/');\n"
            "\t\tprogram_invocation_short_name = slash == NULL ? argv[0] : slash + 1;\n"
            "\t}"
        )
        if text.count(signature) != 1:
            raise RuntimeError("Kmod standalone-main precondition failed")
        text = text.replace(signature, replacement, 1)
        text += (
            "\n#ifndef RUSTBOX_MULTICALL\n"
            "int main(int argc, char *argv[])\n"
            "{\n"
            "\treturn rustbox_kmod_main(argc, argv);\n"
            "}\n"
            "#endif\n"
        )
        main_c.write_text(text)

        file_c = staged / "libkmod/libkmod-file.c"
        file_text = file_c.read_text()
        array_size = "i < ARRAY_SIZE(comp_types)"
        explicit_size = "i < sizeof(comp_types) / sizeof(comp_types[0])"
        if file_text.count(array_size) != 1:
            raise RuntimeError("Kmod compression-table loop precondition failed")
        file_c.write_text(file_text.replace(array_size, explicit_size, 1))

        module_c = staged / "libkmod/libkmod-module.c"
        module_text = module_c.read_text()
        lookup_size = "ARRAY_SIZE(lookup)"
        lookup_explicit = "sizeof(lookup) / sizeof(lookup[0])"
        elvis = 'options ?: ""'
        ternary = 'options != NULL ? options : ""'
        if module_text.count(lookup_size) != 2 or module_text.count(elvis) != 2:
            raise RuntimeError("Kmod module lookup/option precondition failed")
        module_c.write_text(
            module_text.replace(lookup_size, lookup_explicit).replace(elvis, ternary)
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
            raise RuntimeError("normalization changed the Kmod file set")
        changed = sorted(
            name for name in canonical_files
            if sha256(canonical / name) != sha256(staged / name)
        )
        if changed != ["libkmod/libkmod-file.c", "libkmod/libkmod-module.c", "tools/kmod.c"]:
            raise RuntimeError(f"unexpected normalized Kmod sources: {changed}")

        manifest = {
            "schema": 1,
            "release": "34.3",
            "canonical_archive_sha256": release["sha256"],
            "canonical_tree_sha256": tree_digest(canonical),
            "normalized_tree_sha256": tree_digest(staged),
            "changed_sources": changed,
            "entrypoint": "rustbox_kmod_main",
            "conditional": "RUSTBOX_MULTICALL",
            "engine": "exact deterministic source rewrite",
            "transformations": [{
                "source": "libkmod/libkmod-file.c",
                "canonical_sha256": sha256(canonical / "libkmod/libkmod-file.c"),
                "normalized_sha256": sha256(staged / "libkmod/libkmod-file.c"),
                "operation": (
                    "replace ARRAY_SIZE(comp_types) with the equivalent "
                    "sizeof(comp_types) / sizeof(comp_types[0]) expression"
                ),
                "semantic_basis": (
                    "comp_types is a complete file-scope array at the use site; "
                    "both constant expressions are definitionally identical"
                ),
            }, {
                "source": "libkmod/libkmod-module.c",
                "canonical_sha256": sha256(canonical / "libkmod/libkmod-module.c"),
                "normalized_sha256": sha256(staged / "libkmod/libkmod-module.c"),
                "operation": (
                    "expand two local-array ARRAY_SIZE expressions and two GNU "
                    "omitted-middle-operand conditionals into standard C forms"
                ),
                "semantic_basis": (
                    "each lookup object is a complete local array at its use; "
                    "x ?: y is defined by GNU C as x ? x : y with x evaluated once, "
                    "and options is an already evaluated local pointer"
                ),
            }, {
                "source": "tools/kmod.c",
                "canonical_sha256": sha256(canonical / "tools/kmod.c"),
                "normalized_sha256": sha256(staged / "tools/kmod.c"),
                "operation": (
                    "export rustbox_kmod_main, derive glibc program-name globals "
                    "from argv[0], and retain a conditional standalone wrapper"
                ),
                "semantic_basis": (
                    "glibc initializes the same globals from argv[0] for standalone "
                    "execution; explicit initialization preserves that policy when "
                    "the engine is entered through a multicall dispatcher"
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
    print(json.dumps({"changed_sources": changed, "entrypoint": "rustbox_kmod_main"},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
