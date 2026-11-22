#!/usr/bin/env python3
"""Stage GNU Gawk with defined field storage and a multicall entrypoint."""

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
        raise RuntimeError(f"Gawk {label} precondition failed in {path}")
    path.write_text(text.replace(old, new))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    canonical = repository / "work/upstream/gawk-5.4.0"
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["gawk"]
    state = json.loads((repository / "work/upstream/.state/gawk.json").read_text())
    for key in ("version", "sha256", "signature_sha256", "signer_fingerprint", "key_sha256"):
        if state.get(key) != release[key]:
            raise RuntimeError(f"GNU Gawk source state changed at {key}")
    if not state["signature_verified"]:
        raise RuntimeError("canonical GNU Gawk signature state is incomplete")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    try:
        shutil.copytree(canonical, staged, symlinks=True)

        main_c = staged / "main.c"
        replace_once(
            main_c,
            "int\nmain(int argc, char **argv)\n{",
            "int\nrustbox_gawk_main(int argc, char **argv)\n{",
            "multicall entrypoint",
        )
        with main_c.open("a") as stream:
            stream.write(
                "\n#ifndef RUSTBOX_MULTICALL\n"
                "int\nmain(int argc, char **argv)\n"
                "{\n\treturn rustbox_gawk_main(argc, argv);\n}\n"
                "#endif\n"
            )

        readdir = staged / "extension/readdir.c"
        replace_once(
            readdir,
            "\tunion {\n\t\tawk_fieldwidth_info_t fw;\n"
            "\t\tchar buf[awk_fieldwidth_info_size(3)];\n\t} u;",
            "\tunion {\n"
            "\t\tstruct {\n"
            "\t\t\tawk_fieldwidth_info_t head;\n"
            "\t\t\tstruct awk_field_info extra[2];\n"
            "\t\t} fw3;\n"
            "\t\tchar buf[awk_fieldwidth_info_size(3)];\n"
            "\t} u;",
            "three-field storage declaration",
        )
        replace_once(readdir, "#define fw u.fw\n", "#define fw u.fw3.head\n#define fw_extra u.fw3.extra\n",
                     "field storage aliases")
        for old, new, label in (
            ("the_dir->fw.fields[1].len", "the_dir->fw_extra[0].len", "field two length"),
            ("the_dir->fw.fields[2].len", "the_dir->fw_extra[1].len", "field three length"),
            ("the_dir->fw.fields[1].skip", "the_dir->fw_extra[0].skip", "field two skip"),
            ("the_dir->fw.fields[2].skip", "the_dir->fw_extra[1].skip", "field three skip"),
        ):
            replace_once(readdir, old, new, label)
        replace_once(
            readdir,
            "#pragma GCC diagnostic push\n#pragma GCC diagnostic ignored \"-Warray-bounds\"\n"
            "\tthe_dir->fw.fields[0].skip = 0;\t/* no leading space */\n",
            "\tthe_dir->fw.fields[0].skip = 0;\t/* no leading space */\n",
            "obsolete bounds suppression prefix",
        )
        replace_once(
            readdir,
            "\tthe_dir->fw_extra[1].skip = 1;\t/* single '/' separator */\n"
            "#pragma GCC diagnostic pop\n",
            "\tthe_dir->fw_extra[1].skip = 1;\t/* single '/' separator */\n",
            "obsolete bounds suppression suffix",
        )

        canonical_files = {p.relative_to(canonical).as_posix() for p in canonical.rglob("*") if p.is_file()}
        staged_files = {p.relative_to(staged).as_posix() for p in staged.rglob("*") if p.is_file()}
        if canonical_files != staged_files:
            raise RuntimeError("normalization changed the GNU Gawk file set")
        changed = sorted(name for name in canonical_files
                         if sha256(canonical / name) != sha256(staged / name))
        if changed != ["extension/readdir.c", "main.c"]:
            raise RuntimeError(f"unexpected normalized GNU Gawk sources: {changed}")
        manifest = {
            "schema": 1,
            "release": "5.4.0",
            "canonical_archive_sha256": release["sha256"],
            "canonical_tree_sha256": tree_digest(canonical),
            "normalized_tree_sha256": tree_digest(staged),
            "changed_sources": changed,
            "entrypoints": 1,
            "conditional": "RUSTBOX_MULTICALL",
            "engine": "exact deterministic source rewrite",
            "transformations": [
                {
                    "source": "extension/readdir.c",
                    "canonical_sha256": sha256(canonical / "extension/readdir.c"),
                    "normalized_sha256": sha256(staged / "extension/readdir.c"),
                    "operation": "store fields two and three in declared trailing awk_field_info objects",
                    "semantic_basis": "the API allocation remains exactly awk_fieldwidth_info_size(3); only accesses beyond the public one-element compatibility member are redirected to declared adjacent objects",
                },
                {
                    "source": "main.c",
                    "canonical_sha256": sha256(canonical / "main.c"),
                    "normalized_sha256": sha256(staged / "main.c"),
                    "operation": "export rustbox_gawk_main and retain a conditional standalone wrapper",
                },
            ],
        }
        if output.exists():
            shutil.rmtree(output)
        staged.rename(output)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"changed_sources": changed, "entrypoints": 1,
                      "undefined_behavior": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
