#!/usr/bin/env python3
"""Stage Ncurses with deterministic, translation-friendly C normalization."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path


ENTRYPOINTS = {
    "progs/clear.c": ("rustbox_clear_main", "int\nmain(\n\tint argc GCC_UNUSED,\n\tchar *argv[]GCC_UNUSED)\n{"),
    "progs/infocmp.c": ("rustbox_infocmp_main", "int\nmain(int argc, char *argv[])\n{"),
    "progs/tabs.c": ("rustbox_tabs_main", "int\nmain(int argc, char *argv[])\n{"),
    "progs/tic.c": ("rustbox_tic_main", "int\nmain(int argc, char *argv[])\n{"),
    "progs/toe.c": ("rustbox_toe_main", "int\nmain(int argc, char *argv[])\n{"),
    "progs/tput.c": ("rustbox_tput_main", "int\nmain(int argc, char **argv)\n{"),
    "progs/tset.c": ("rustbox_tset_main", "int\nmain(int argc, char **argv)\n{"),
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


def export_entrypoint(path: Path, exported: str, signature: str) -> None:
    text = path.read_text()
    if text.count(signature) != 1:
        raise RuntimeError(f"Ncurses entrypoint precondition failed: {path}")
    prefix, suffix = signature.split("main", 1)
    text = text.replace(signature, prefix + exported + suffix)
    text += (
        "\n#ifndef RUSTBOX_MULTICALL\n"
        "int\n"
        "main(int argc, char **argv)\n"
        "{\n"
        f"    return {exported}(argc, argv);\n"
        "}\n"
        "#endif\n"
    )
    path.write_text(text)


def normalize_byte_shifts(path: Path) -> int:
    text = path.read_text()
    old = "(ch << (8 * j))"
    new = "((unsigned) ch << (8 * j))"
    count = text.count(old)
    if count != 3:
        raise RuntimeError(f"Ncurses byte-shift precondition failed: {path}: {count}")
    path.write_text(text.replace(old, new))
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    repository = args.repository.resolve()
    canonical = repository / "work/upstream/ncurses-6.6"
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["ncurses"]
    state = json.loads((repository / "work/upstream/.state/ncurses.json").read_text())
    for key in ("version", "sha256", "signature_sha256", "signer_fingerprint", "key_sha256"):
        if state.get(key) != release[key]:
            raise RuntimeError(f"Ncurses source state changed at {key}")
    if not state["signature_verified"]:
        raise RuntimeError("canonical Ncurses signature state is incomplete")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    changed: list[str] = []
    try:
        shutil.copytree(canonical, staged, symlinks=True)
        transformations: list[dict[str, object]] = []
        for relative, (exported, signature) in ENTRYPOINTS.items():
            path = staged / relative
            canonical_digest = sha256(canonical / relative)
            export_entrypoint(path, exported, signature)
            transformations.append({
                "source": relative,
                "canonical_sha256": canonical_digest,
                "normalized_sha256": sha256(path),
                "operation": f"export {exported} and retain a conditional standalone main wrapper",
            })

        relative = "ncurses/tinfo/read_entry.c"
        path = staged / relative
        canonical_digest = sha256(canonical / relative)
        shifts = normalize_byte_shifts(path)
        transformations.append({
            "source": relative,
            "canonical_sha256": canonical_digest,
            "normalized_sha256": sha256(path),
            "operation": "promote each input byte to unsigned before left shift",
            "sites": shifts,
            "semantic_basis": "the input is unsigned char; unsigned promotion preserves the intended bit pattern while removing signed-left-shift UB",
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
            raise RuntimeError("normalization added or removed Ncurses source-tree files")
        changed = sorted(
            name for name in canonical_files
            if sha256(canonical / name) != sha256(staged / name)
        )
        expected = sorted([*ENTRYPOINTS, "ncurses/tinfo/read_entry.c"])
        if changed != expected:
            raise RuntimeError(f"unexpected Ncurses normalized sources: {changed}")

        manifest = {
            "schema": 1,
            "release": release["version"],
            "canonical_archive_sha256": release["sha256"],
            "canonical_tree_sha256": tree_digest(canonical),
            "normalized_tree_sha256": tree_digest(staged),
            "changed_sources": changed,
            "entrypoints": len(ENTRYPOINTS),
            "public_native_names": 10,
            "conditional": "RUSTBOX_MULTICALL",
            "engine": "exact deterministic source rewrite",
            "transformations": transformations,
        }
        if output.exists():
            shutil.rmtree(output)
        staged.rename(output)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"changed_sources": len(changed), "entrypoints": len(ENTRYPOINTS)},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
