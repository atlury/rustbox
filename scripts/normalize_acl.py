#!/usr/bin/env python3
"""Stage acl with deterministic translation-friendly normalization."""

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
        raise RuntimeError(f"acl {label} precondition failed in {path}")
    path.write_text(text.replace(old, new))


def export_entrypoint(path: Path, signature: str, replacement: str, name: str) -> None:
    replace_once(path, signature, replacement, name)
    path.write_text(path.read_text() + (
        "\n#ifndef RUSTBOX_MULTICALL\n"
        "int\n"
        "main(int argc, char **argv)\n"
        "{\n"
        f"\treturn {name}(argc, argv);\n"
        "}\n"
        "#endif\n"
    ))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    canonical = repository / "work/upstream/acl-2.4.0"
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["acl"]
    state = json.loads((repository / "work/upstream/.state/acl.json").read_text())
    for key in ("version", "sha256", "signature_sha256", "signer_fingerprint", "key_sha256"):
        if state.get(key) != release[key]:
            raise RuntimeError(f"acl source state changed at {key}")
    if not state["signature_verified"]:
        raise RuntimeError("canonical acl release signature is not verified")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    try:
        shutil.copytree(canonical, staged, symlinks=True)

        chacl = staged / "tools/chacl.c"
        export_entrypoint(
            chacl, "int\nmain(int argc, char *argv[])\n{",
            "int\nrustbox_chacl_main(int argc, char *argv[])\n{", "rustbox_chacl_main",
        )
        getfacl = staged / "tools/getfacl.c"
        export_entrypoint(
            getfacl, "int main(int argc, char *argv[])\n{",
            "int rustbox_getfacl_main(int argc, char *argv[])\n{", "rustbox_getfacl_main",
        )
        setfacl = staged / "tools/setfacl.c"
        export_entrypoint(
            setfacl, "int main(int argc, char *argv[])\n{",
            "int rustbox_setfacl_main(int argc, char *argv[])\n{", "rustbox_setfacl_main",
        )

        replace_once(
            staged / "libacl/__libobj.c",
            "\tobj_prefix *obj_p = ((obj_prefix *)ext_p)-1;\n"
            "\tif (!ext_p) {\n",
            "\tobj_prefix *obj_p;\n"
            "\tif (!ext_p) {\n",
            "external object null check",
        )
        replace_once(
            staged / "libacl/__libobj.c",
            "\t\terrno = EINVAL;\n\t\treturn NULL;\n\t}\n"
            "\treturn __acl_check_obj_p(obj_p, magic);\n",
            "\t\terrno = EINVAL;\n\t\treturn NULL;\n\t}\n"
            "\tobj_p = ((obj_prefix *)ext_p)-1;\n"
            "\treturn __acl_check_obj_p(obj_p, magic);\n",
            "external object conversion after null check",
        )
        replace_once(
            staged / "libacl/acl_free.c",
            "\tobj_prefix *int_p = ((obj_prefix *)obj_p)-1;\n"
            "\tif (!obj_p || !int_p) {\n",
            "\tobj_prefix *int_p;\n"
            "\tif (!obj_p) {\n",
            "free object null check",
        )
        replace_once(
            staged / "libacl/acl_free.c",
            "\t\terrno = EINVAL;\n\t\treturn -1;\n\t}\n\n\n"
            "\tswitch(int_p->p_magic) {\n",
            "\t\terrno = EINVAL;\n\t\treturn -1;\n\t}\n"
            "\tint_p = ((obj_prefix *)obj_p)-1;\n\n\n"
            "\tswitch(int_p->p_magic) {\n",
            "free object conversion after null check",
        )
        replace_once(
            setfacl,
            "\t\t\t\trestore_args = realloc(restore_args,\n"
            "\t\t\t\t\topt_restore_count * sizeof(*restore_args));\n"
            "\t\t\t\tif (!restore_args) {\n"
            "\t\t\t\t\tfprintf(stderr, \"%s: %s\\n\", progname, strerror(errno));\n"
            "\t\t\t\t\tstatus = 1;\n"
            "\t\t\t\t\tgoto cleanup;\n"
            "\t\t\t\t}\n",
            "\t\t\t\t{\n"
            "\t\t\t\t\tchar **new_restore_args = realloc(restore_args,\n"
            "\t\t\t\t\t\topt_restore_count * sizeof(*restore_args));\n"
            "\t\t\t\t\tif (!new_restore_args) {\n"
            "\t\t\t\t\t\tfprintf(stderr, \"%s: %s\\n\", progname, strerror(errno));\n"
            "\t\t\t\t\t\tstatus = 1;\n"
            "\t\t\t\t\t\tgoto cleanup;\n"
            "\t\t\t\t\t}\n"
            "\t\t\t\t\trestore_args = new_restore_args;\n"
            "\t\t\t\t}\n",
            "owned realloc result",
        )

        canonical_files = {
            path.relative_to(canonical).as_posix() for path in canonical.rglob("*") if path.is_file()
        }
        staged_files = {
            path.relative_to(staged).as_posix() for path in staged.rglob("*") if path.is_file()
        }
        if canonical_files != staged_files:
            raise RuntimeError("normalization added or removed acl source-tree files")
        changed = sorted(
            name for name in canonical_files if sha256(canonical / name) != sha256(staged / name)
        )
        expected = [
            "libacl/__libobj.c", "libacl/acl_free.c", "tools/chacl.c",
            "tools/getfacl.c", "tools/setfacl.c",
        ]
        if changed != expected:
            raise RuntimeError(f"unexpected acl normalized sources: {changed}")

        operations = {
            "libacl/__libobj.c": "perform external-object pointer subtraction only after validating non-null input",
            "libacl/acl_free.c": "perform internal-object pointer subtraction only after validating non-null input",
            "tools/chacl.c": "export the chacl multicall entrypoint while retaining the standalone wrapper",
            "tools/getfacl.c": "export the getfacl multicall entrypoint while retaining the standalone wrapper",
            "tools/setfacl.c": "export the setfacl multicall entrypoint and retain realloc ownership until allocation succeeds",
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
