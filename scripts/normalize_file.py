#!/usr/bin/env python3
"""Stage File with deterministic Coccinelle and multicall normalization."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
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
    canonical = repository / "work/upstream/file-5.48"
    state = json.loads((repository / "work/upstream/.state/file.json").read_text())
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["file"]
    for key in ("version", "sha256", "signature_sha256", "signer_fingerprint", "key_sha256"):
        if state.get(key) != release[key]:
            raise RuntimeError(f"File source state changed at {key}")
    if not state["signature_verified"]:
        raise RuntimeError("canonical File release signature is not verified")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    changes: list[dict[str, str]] = []
    try:
        shutil.copytree(canonical, staged, symlinks=True)

        softmagic = staged / "src/softmagic.c"
        before = softmagic.read_text()
        if before.count("\tintmax_t offset;\n") != 1:
            raise RuntimeError("do_ops offset normalization precondition failed")
        subprocess.run(
            [
                "spatch",
                "--very-quiet",
                "--sp-file",
                str(repository / "normalizations/file-do-ops-offset.cocci"),
                "--macro-file",
                str(repository / "normalizations/file-coccinelle.h"),
                "--in-place",
                str(softmagic),
            ],
            check=True,
        )
        after = softmagic.read_text()
        if after.count("\tintmax_t offset = lhs;\n") != 1 or "\tintmax_t offset;\n" in after:
            raise RuntimeError("Coccinelle did not initialize do_ops offset exactly once")
        changes.append(
            {
                "source": "src/softmagic.c",
                "canonical_sha256": sha256(canonical / "src/softmagic.c"),
                "normalized_sha256": sha256(softmagic),
                "operation": "initialize do_ops offset to the identity lhs before dispatching a validated operation",
                "engine": "Coccinelle 1.3.3 semantic patch",
            }
        )

        apprentice = staged / "src/apprentice.c"
        before_apprentice = apprentice.read_text()
        apprentice_declarations = (
            "\tstatic const size_t nm = sizeof(*map->nmagic) * MAGIC_SETS;\n"
            "\tstatic const size_t m = sizeof(**map->magic);\n"
            "\tint fd = -1;\n"
            "\tsize_t len;\n"
        )
        apprentice_declarations_normalized = (
            "\tstatic const size_t magic_set_sizes_bytes =\n"
            "\t    sizeof(*map->nmagic) * MAGIC_SETS;\n"
            "\tstatic const size_t magic_record_size = sizeof(**map->magic);\n"
            "\tint fd = -1;\n"
            "\tsize_t database_len;\n"
        )
        apprentice_write = (
            "\t\tlen = m * map->nmagic[i];\n"
            "\t\tif (write(fd, map->magic[i], len) != CAST(ssize_t, len)) {\n"
        )
        apprentice_write_normalized = (
            "\t\tdatabase_len = magic_record_size * map->nmagic[i];\n"
            "\t\tif (write(fd, map->magic[i], database_len) !=\n"
            "\t\t    CAST(ssize_t, database_len)) {\n"
        )
        if before_apprentice.count(apprentice_declarations) != 1:
            raise RuntimeError("apprentice_compile declaration normalization precondition failed")
        if before_apprentice.count(apprentice_write) != 1:
            raise RuntimeError("apprentice_compile write normalization precondition failed")
        after_apprentice = before_apprentice.replace(
            apprentice_declarations, apprentice_declarations_normalized
        ).replace(apprentice_write, apprentice_write_normalized)
        if after_apprentice.count("memcpy(hdr.h + 2, map->nmagic, nm);") != 1:
            raise RuntimeError("apprentice_compile header-size normalization precondition failed")
        after_apprentice = after_apprentice.replace(
            "memcpy(hdr.h + 2, map->nmagic, nm);",
            "memcpy(hdr.h + 2, map->nmagic, magic_set_sizes_bytes);",
        )
        allocation_block = (
            "\t\tstatic const size_t len = sizeof(*m) * ALLOC_CHUNK;\n"
            "\t\tif (me->mp != NULL)\n"
            "\t\t\treturn 1;\n"
            "\t\tif ((m = CAST(struct magic *, malloc(len))) == NULL) {\n"
            "\t\t\tfile_oomem(ms, len);\n"
        )
        allocation_block_normalized = (
            "\t\tstatic const size_t magic_allocation_size =\n"
            "\t\t    sizeof(*m) * ALLOC_CHUNK;\n"
            "\t\tif (me->mp != NULL)\n"
            "\t\t\treturn 1;\n"
            "\t\tif ((m = CAST(struct magic *, malloc(magic_allocation_size))) == NULL) {\n"
            "\t\t\tfile_oomem(ms, magic_allocation_size);\n"
        )
        if after_apprentice.count(allocation_block) != 1:
            raise RuntimeError("magic allocation-size normalization precondition failed")
        after_apprentice = after_apprentice.replace(
            allocation_block, allocation_block_normalized
        )
        apprentice.write_text(after_apprentice)
        changes.append(
            {
                "source": "src/apprentice.c",
                "canonical_sha256": sha256(canonical / "src/apprentice.c"),
                "normalized_sha256": sha256(apprentice),
                "operation": "give three C2Rust-lifted size variables globally unique names",
                "engine": "exact deterministic translator-compatibility rewrite",
            }
        )

        before_fp = softmagic.read_text()
        fp_replacements = {
            "matched = isunordered(fl, fv) ? 1 : fv != fl;": "matched = fv != fl;",
            "matched = isunordered(fl, fv) ? 0 : fv == fl;": "matched = fv == fl;",
            "matched = isgreater(fv, fl);": "matched = fv > fl;",
            "matched = isless(fv, fl);": "matched = fv < fl;",
            "matched = isunordered(dv, dl) ? 1 : dv != dl;": "matched = dv != dl;",
            "matched = isunordered(dv, dl) ? 0 : dv == dl;": "matched = dv == dl;",
            "matched = isgreater(dv, dl);": "matched = dv > dl;",
            "matched = isless(dv, dl);": "matched = dv < dl;",
        }
        after_fp = before_fp
        for old, new in fp_replacements.items():
            if after_fp.count(old) != 1:
                raise RuntimeError(f"floating comparison normalization precondition failed: {old}")
            after_fp = after_fp.replace(old, new)
        softmagic.write_text(after_fp)
        if any(name in after_fp for name in ("isunordered(", "isgreater(", "isless(")):
            raise RuntimeError("C2Rust-incompatible floating comparison macro remains")
        changes.append(
            {
                "source": "src/softmagic.c",
                "canonical_sha256": sha256(canonical / "src/softmagic.c"),
                "normalized_sha256": sha256(softmagic),
                "operation": "spell eight IEEE-754 comparisons with equivalent C operators instead of unsupported Clang builtins",
                "engine": "exact deterministic translator-compatibility rewrite",
            }
        )

        entrypoint = staged / "src/file.c"
        before = entrypoint.read_text()
        signature = "int\nmain(int argc, char *argv[])\n{"
        replacement = (
            "int rustbox_file_main(int argc, char *argv[]);\n\n"
            "int\n"
            "rustbox_file_main(int argc, char *argv[])\n{"
        )
        if before.count(signature) != 1 or "rustbox_file_main" in before:
            raise RuntimeError("File entrypoint normalization precondition failed")
        wrapper = (
            "\n#ifndef RUSTBOX_MULTICALL\n"
            "int\n"
            "main(int argc, char *argv[])\n"
            "{\n"
            "\treturn rustbox_file_main(argc, argv);\n"
            "}\n"
            "#endif\n"
        )
        entrypoint.write_text(before.replace(signature, replacement) + wrapper)
        if entrypoint.read_text().count("rustbox_file_main") != 3:
            raise RuntimeError("File entrypoint normalization postcondition failed")
        changes.append(
            {
                "source": "src/file.c",
                "canonical_sha256": sha256(canonical / "src/file.c"),
                "normalized_sha256": sha256(entrypoint),
                "operation": "export rustbox_file_main with a conditional standalone main wrapper",
                "engine": "exact deterministic source rewrite",
            }
        )

        canonical_files = {
            path.relative_to(canonical).as_posix()
            for path in canonical.rglob("*")
            if path.is_file()
        }
        staged_files = {
            path.relative_to(staged).as_posix()
            for path in staged.rglob("*")
            if path.is_file()
        }
        if canonical_files != staged_files:
            raise RuntimeError("normalization added or removed source-tree files")
        changed = sorted(
            relative
            for relative in canonical_files
            if sha256(canonical / relative) != sha256(staged / relative)
        )
        if changed != ["src/apprentice.c", "src/file.c", "src/softmagic.c"]:
            raise RuntimeError(f"unexpected normalized source changes: {changed}")

        manifest = {
            "schema": 1,
            "release": release["version"],
            "canonical_archive_sha256": release["sha256"],
            "canonical_tree_sha256": tree_digest(canonical),
            "normalized_tree_sha256": tree_digest(staged),
            "changed_sources": changed,
            "transformations": changes,
            "conditional": "RUSTBOX_MULTICALL",
            "engines": [
                "Coccinelle 1.3.3 semantic patch",
                "exact deterministic source rewrite",
                "exact deterministic translator-compatibility rewrite",
            ],
        }
        if output.exists():
            shutil.rmtree(output)
        staged.rename(output)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"changed_sources": len(changed), "entrypoints": 1}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
