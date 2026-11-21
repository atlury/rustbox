#!/usr/bin/env python3
"""Stage LZ4 with deterministic, translation-friendly normalization."""

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
        raise RuntimeError(f"LZ4 {label} precondition failed in {path}")
    path.write_text(text.replace(old, new))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    canonical = repository / "work/upstream/lz4-1.11.1"
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["lz4"]
    state = json.loads((repository / "work/upstream/.state/lz4.json").read_text())
    for key in ("version", "sha256", "checksum_sha256", "tag", "commit"):
        if state.get(key) != release[key]:
            raise RuntimeError(f"LZ4 source state changed at {key}")
    if not state["integrity_verified"] or state["signature_verified"]:
        raise RuntimeError("canonical LZ4 checksum state is incomplete or misrepresented")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    try:
        shutil.copytree(canonical, staged, symlinks=True)
        cli = staged / "programs/lz4cli.c"
        frame = staged / "lib/lz4frame.c"

        replace_once(
            cli,
            "int main(int argCount, const char** argv)\n{",
            "int rustbox_lz4_main(int argCount, char** argv)\n{",
            "multicall entrypoint",
        )
        cli.write_text(cli.read_text() + (
            "\n#ifndef RUSTBOX_MULTICALL\n"
            "int main(int argc, char **argv)\n"
            "{\n"
            "    return rustbox_lz4_main(argc, argv);\n"
            "}\n"
            "#endif\n"
        ))
        replace_once(
            cli,
            '    DISPLAYOUT( "-0  => Default level, identical to -%u \\n", LZ4_CLEVEL_DEFAULT);',
            '    DISPLAYOUT( "-0  => Default level, identical to -%u \\n", (unsigned)LZ4_CLEVEL_DEFAULT);',
            "help vararg signedness",
        )
        replace_once(
            cli,
            "            strcpy(dynNameSpace, input_filename);\n"
            "            strcat(dynNameSpace, LZ4_EXTENSION);",
            "            memcpy(dynNameSpace, input_filename, l);\n"
            "            memcpy(dynNameSpace + l, LZ4_EXTENSION, sizeof(LZ4_EXTENSION));",
            "bounded automatic output name",
        )
        for line, label in (
            (
                "        memcpy(dctx->tmpOutBuffer + dctx->dictSize, dstPtr, dstSize);",
                "existing dictionary zero-length copy",
            ),
            (
                "        memcpy(dctx->tmpOutBuffer + preserveSize, dstPtr, dstSize);",
                "joined dictionary zero-length copy",
            ),
        ):
            replace_once(frame, line, line.replace("memcpy", "if (dstSize != 0) memcpy"), label)
        io = staged / "programs/lz4io.c"
        replace_once(
            io,
            "static const char* LZ4IO_toHuman(long double size, char* buf)",
            "static const char* LZ4IO_toHuman(double size, char* buf)",
            "variadic-compatible human-size value",
        )
        text = io.read_text()
        if text.count("(long double)") != 2:
            raise RuntimeError("LZ4 human-size call-site precondition failed")
        text = text.replace("(long double)", "(double)")
        if text.count('"%.2Lf%c"') != 1:
            raise RuntimeError("LZ4 human-size format precondition failed")
        io.write_text(text.replace('"%.2Lf%c"', '"%.2f%c"'))

        canonical_files = {
            path.relative_to(canonical).as_posix() for path in canonical.rglob("*") if path.is_file()
        }
        staged_files = {
            path.relative_to(staged).as_posix() for path in staged.rglob("*") if path.is_file()
        }
        if canonical_files != staged_files:
            raise RuntimeError("normalization added or removed LZ4 source-tree files")
        changed = sorted(
            name for name in canonical_files if sha256(canonical / name) != sha256(staged / name)
        )
        expected = ["lib/lz4frame.c", "programs/lz4cli.c", "programs/lz4io.c"]
        if changed != expected:
            raise RuntimeError(f"unexpected LZ4 normalized sources: {changed}")

        operations = {
            "lib/lz4frame.c": (
                "make zero-length public dictionary copies explicit before invoking memcpy"
            ),
            "programs/lz4cli.c": (
                "export a standard char** multicall entrypoint while retaining a standalone wrapper; "
                "match the unsigned help vararg; replace output-name strcpy/strcat with exact memcpy"
            ),
            "programs/lz4io.c": (
                "use double for the uint64 human-size display path so translated C variadics retain the native ABI"
            ),
        }
        manifest = {
            "schema": 1,
            "release": release["version"],
            "canonical_archive_sha256": release["sha256"],
            "canonical_tree_sha256": tree_digest(canonical),
            "normalized_tree_sha256": tree_digest(staged),
            "changed_sources": changed,
            "conditional": "RUSTBOX_MULTICALL",
            "compiler_normalization": "LZ4_FORCE_MEMORY_ACCESS=0 selects the upstream portable memcpy implementation",
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
    print(json.dumps({"changed_sources": changed, "entrypoints": 1}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
