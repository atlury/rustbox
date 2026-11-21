#!/usr/bin/env python3
"""Stage attr with deterministic translation-friendly normalization."""

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
        raise RuntimeError(f"attr {label} precondition failed in {path}")
    path.write_text(text.replace(old, new))


def export_entrypoint(path: Path, signature: str, replacement: str, name: str) -> None:
    replace_once(path, signature, replacement, name)
    wrapper = (
        "\n#ifndef RUSTBOX_MULTICALL\n"
        "int\n"
        "main(int argc, char **argv)\n"
        "{\n"
        f"\treturn {name}(argc, argv);\n"
        "}\n"
        "#endif\n"
    )
    path.write_text(path.read_text() + wrapper)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    canonical = repository / "work/upstream/attr-2.6.0"
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["attr"]
    state = json.loads((repository / "work/upstream/.state/attr.json").read_text())
    for key in ("version", "sha256", "signature_sha256", "signer_fingerprint", "key_sha256"):
        if state.get(key) != release[key]:
            raise RuntimeError(f"attr source state changed at {key}")
    if not state["signature_verified"]:
        raise RuntimeError("canonical attr release signature is not verified")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    try:
        shutil.copytree(canonical, staged, symlinks=True)

        attr = staged / "tools/attr.c"
        export_entrypoint(
            attr,
            "int\nmain(int argc, char **argv)\n{",
            "int\nrustbox_attr_main(int argc, char **argv)\n{",
            "rustbox_attr_main",
        )
        replace_once(
            attr,
            'Attribute \\"%s\\" has a %d byte value for %s\\n',
            'Attribute \\"%s\\" has a %u byte value for %s\\n',
            "unsigned attribute length format",
        )

        getfattr = staged / "tools/getfattr.c"
        export_entrypoint(
            getfattr,
            "int main(int argc, char *argv[])\n{",
            "int rustbox_getfattr_main(int argc, char *argv[])\n{",
            "rustbox_getfattr_main",
        )
        replace_once(
            getfattr,
            "\tqsort(names, num_names, sizeof(*names), pstrcmp);",
            "\tif (num_names)\n\t\tqsort(names, num_names, sizeof(*names), pstrcmp);",
            "zero-element qsort guard",
        )

        setfattr = staged / "tools/setfattr.c"
        export_entrypoint(
            setfattr,
            "int main(int argc, char *argv[])\n{",
            "int rustbox_setfattr_main(int argc, char *argv[])\n{",
            "rustbox_setfattr_main",
        )
        replace_once(
            setfattr,
            "\t\t\trestore_args = realloc(restore_args,\n"
            "\t\t\t\t\topt_restore * sizeof(*restore_args));\n"
            "\t\t\t\tif (!restore_args) {\n"
            "\t\t\t\t\tperror(progname);\n"
            "\t\t\t\t\texit(1);\n"
            "\t\t\t\t}\n",
            "\t\t\t{\n"
            "\t\t\t\tchar **new_restore_args = realloc(restore_args,\n"
            "\t\t\t\t\topt_restore * sizeof(*restore_args));\n"
            "\t\t\t\tif (!new_restore_args) {\n"
            "\t\t\t\t\tperror(progname);\n"
            "\t\t\t\t\texit(1);\n"
            "\t\t\t\t}\n"
            "\t\t\t\trestore_args = new_restore_args;\n"
            "\t\t\t}\n",
            "owned realloc result",
        )

        canonical_files = {path.relative_to(canonical).as_posix() for path in canonical.rglob("*") if path.is_file()}
        staged_files = {path.relative_to(staged).as_posix() for path in staged.rglob("*") if path.is_file()}
        if canonical_files != staged_files:
            raise RuntimeError("normalization added or removed attr source-tree files")
        changed = sorted(name for name in canonical_files if sha256(canonical / name) != sha256(staged / name))
        if changed != ["tools/attr.c", "tools/getfattr.c", "tools/setfattr.c"]:
            raise RuntimeError(f"unexpected attr normalized sources: {changed}")

        operations = {
            "tools/attr.c": "export multicall entrypoint and print the unsigned attribute length with its matching format",
            "tools/getfattr.c": "export multicall entrypoint and guard the configured-libc zero-element qsort call",
            "tools/setfattr.c": "export multicall entrypoint and retain realloc ownership until allocation succeeds",
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
    print(json.dumps({"changed_sources": changed, "entrypoints": 3}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
