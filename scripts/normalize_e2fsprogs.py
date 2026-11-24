#!/usr/bin/env python3
"""Stage signed E2fsprogs 1.47.4 with exported multicall entrypoints."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path


ENTRYPOINTS = (
    ("badblocks", "misc/badblocks.c"),
    ("debugfs", "debugfs/debugfs.c"),
    ("dumpe2fs", "misc/dumpe2fs.c"),
    ("e2fsck", "e2fsck/unix.c"),
    ("e2image", "misc/e2image.c"),
    ("e2undo", "misc/e2undo.c"),
    ("fsck", "misc/fsck.c"),
    ("logsave", "misc/logsave.c"),
    ("mke2fs", "misc/mke2fs.c"),
    ("resize2fs", "resize/main.c"),
    ("tune2fs", "misc/tune2fs.c"),
    ("chattr", "misc/chattr.c"),
    ("fuse2fs", "misc/fuse2fs.c"),
    ("lsattr", "misc/lsattr.c"),
    ("e2initrd_helper", "misc/e2initrd_helper.c"),
    ("e2freefrag", "misc/e2freefrag.c"),
    ("e4crypt", "misc/e4crypt.c"),
    ("e4defrag", "misc/e4defrag.c"),
    ("filefrag", "misc/filefrag.c"),
    ("mklost_found", "misc/mklost+found.c"),
)

SCRIPTS = ("e2scrub", "e2scrub_all", "compile_et", "mk_cmds")
EXPECTED_STATE = {
    "version": "1.47.4",
    "sha256": "fd5bf388cbdbe006a3d3b318d983b2948382440acc85a87f1e7d108653e8db0b",
    "signature_sha256": "ff826cf86828bf3ed8a7fcbe3e5c0c171f8ebfc5f46c43b27adc1ffc2c6a7b9c",
    "key_sha256": "aefee846527b1ac909a61d1251f0ba67ca66fd5a3be66d97169f5dc18d1720f9",
    "signer_fingerprint": "2B69B954DBFE0879288137C9F2F95956950D81A3",
    "signature_verified": True,
}


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


def wrapper(name: str) -> str:
    symbol = f"rustbox_e2fsprogs_{name}_main"
    if name == "filefrag":
        return (
            "\n#ifndef RUSTBOX_MULTICALL\n"
            "#ifndef __linux__\n"
            "int main(void)\n{\n\treturn " + symbol + "();\n}\n"
            "#else\n"
            "int main(int argc, char **argv)\n{\n\treturn " + symbol + "(argc, argv);\n}\n"
            "#endif\n#endif\n"
        )
    if name == "e2freefrag":
        return (
            "\n#if !defined(RUSTBOX_MULTICALL) && !defined(DEBUGFS)\n"
            "int main(int argc, char **argv)\n"
            "{\n\treturn " + symbol + "(argc, argv);\n}\n"
            "#endif\n"
        )
    return (
        "\n#ifndef RUSTBOX_MULTICALL\n"
        "int main(int argc, char **argv)\n"
        "{\n\treturn " + symbol + "(argc, argv);\n}\n"
        "#endif\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    root = args.repository.resolve()
    canonical = root / "work/upstream/e2fsprogs-1.47.4"
    state = json.loads((root / "work/upstream/.state/e2fsprogs.json").read_text())
    for key, expected in EXPECTED_STATE.items():
        if state.get(key) != expected:
            raise RuntimeError(f"E2fsprogs signed source state changed at {key}")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    transformations = []
    try:
        shutil.copytree(canonical, staged, symlinks=True)
        for name, relative in ENTRYPOINTS:
            path = staged / relative
            text = path.read_text()
            symbol = f"rustbox_e2fsprogs_{name}_main"
            expected = 2 if name == "filefrag" else 1
            pattern = re.compile(r"(?m)^(int[ \t]+)main(?=[ \t]*\()")
            if len(pattern.findall(text)) != expected:
                raise RuntimeError(f"{relative}: standalone-main precondition failed")
            normalized = pattern.sub(r"\1" + symbol, text)
            normalized += wrapper(name)
            path.write_text(normalized)
            transformations.append({
                "source": relative,
                "entrypoint": symbol,
                "canonical_sha256": sha256(canonical / relative),
                "normalized_sha256": sha256(path),
                "operation": "rename the native main and add a conditional standalone wrapper",
                "semantic_basis": (
                    "without RUSTBOX_MULTICALL the wrapper passes argc and argv unchanged "
                    "and returns the exported engine's result unchanged"
                ),
            })

        canonical_files = {
            path.relative_to(canonical).as_posix()
            for path in canonical.rglob("*") if path.is_file()
        }
        staged_files = {
            path.relative_to(staged).as_posix()
            for path in staged.rglob("*") if path.is_file()
        }
        if canonical_files != staged_files:
            raise RuntimeError("normalization changed the E2fsprogs file set")
        changed = sorted(
            name for name in canonical_files
            if sha256(canonical / name) != sha256(staged / name)
        )
        expected_changed = sorted(relative for _, relative in ENTRYPOINTS)
        if changed != expected_changed:
            raise RuntimeError(f"unexpected normalized E2fsprogs sources: {changed}")

        manifest = {
            "schema": 1,
            "release": "1.47.4",
            "canonical_archive_sha256": EXPECTED_STATE["sha256"],
            "canonical_tree_sha256": tree_digest(canonical),
            "normalized_tree_sha256": tree_digest(staged),
            "engine": "exact deterministic source rewrite",
            "conditional": "RUSTBOX_MULTICALL",
            "installed_names": 32,
            "native_names": 28,
            "native_engines": len(ENTRYPOINTS),
            "script_engines": list(SCRIPTS),
            "changed_sources": changed,
            "transformations": transformations,
        }
        if output.exists():
            shutil.rmtree(output)
        staged.rename(output)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "changed_sources": len(changed),
        "native_engines": len(ENTRYPOINTS),
        "script_engines": len(SCRIPTS),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
