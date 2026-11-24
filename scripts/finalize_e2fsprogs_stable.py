#!/usr/bin/env python3
"""Finalize C2Rust E2fsprogs crates without weakening C thread-local state."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from modernize_c2rust_output import (  # noqa: E402
    deduplicate_function_static_exports,
    deduplicate_no_mangle_functions,
    deduplicate_no_mangle_statics,
)


PROGRAMS = (
    "badblocks", "chattr", "debugfs", "dumpe2fs", "e2freefrag", "e2fsck",
    "e2image", "e2initrd_helper", "e2undo", "e4crypt", "e4defrag",
    "filefrag", "fsck", "fuse2fs", "logsave", "lsattr", "mke2fs",
    "mklost_found", "resize2fs", "tune2fs",
)
TLS_PROGRAMS = frozenset({
    "badblocks", "chattr", "debugfs", "dumpe2fs", "e2freefrag", "e2fsck",
    "e2image", "e2initrd_helper", "e2undo", "e4defrag", "fuse2fs",
    "lsattr", "mke2fs", "resize2fs", "tune2fs",
})
MISSING_VARIADIC_GATE_PROGRAMS = frozenset({
    "filefrag", "fsck", "logsave", "mklost_found",
})
RAW_POINTER = re.compile(r"\*(?:mut|const)\s+")
HOLE = re.compile(
    r"\b(?:todo|unimplemented)!\s*\(|"
    r"panic!\s*\(\s*\"(?:unimplemented|unsupported)|"
    r"C2Rust.*(?:ERROR|unsupported)|Translation failed|translation failed"
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(path: Path, old: str, new: str, reason: str) -> dict[str, str]:
    text = path.read_text()
    if text.count(old) != 1 or new in text:
        raise RuntimeError(f"E2fsprogs repair anchor changed: {path}: {reason}")
    before = digest(path)
    path.write_text(text.replace(old, new, 1))
    return {
        "path": str(path),
        "reason": reason,
        "before_sha256": before,
        "after_sha256": digest(path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--program", choices=PROGRAMS, required=True)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source = args.input.resolve()
    output = args.output.resolve()
    if not (source / "Cargo.toml").is_file() or source == output or output.is_symlink():
        raise RuntimeError("E2fsprogs finalizer requires distinct real directories")
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    try:
        shutil.copytree(source, staged, ignore=shutil.ignore_patterns("target", "Cargo.lock"))
        rust_sources = sorted(staged.rglob("*.rs"))
        feature = "#![feature(thread_local)]"
        feature_gates = sum(path.read_text().count(feature) for path in rust_sources)
        attributes = sum(path.read_text().count("#[thread_local]") for path in rust_sources)
        expected_tls = int(args.program in TLS_PROGRAMS)
        if (feature_gates, attributes) != (expected_tls, expected_tls):
            raise RuntimeError(
                f"E2fsprogs TLS inventory changed for {args.program}: "
                f"{feature_gates} gates/{attributes} attributes"
            )
        toolchain = (staged / "rust-toolchain.toml").read_text()
        if toolchain.count("nightly-2023-04-15") != 1:
            raise RuntimeError("E2fsprogs C2Rust nightly pin changed")

        changes = [replace_once(
            staged / "lib.rs",
            "#![allow(dead_code)]\n",
            "#![allow(dead_code)]\n#![allow(deref_nullptr)]\n",
            "permit C offsetof/container_of raw-address expressions without dereference",
        )]
        if args.program in MISSING_VARIADIC_GATE_PROGRAMS:
            va_list_uses = sum(
                path.read_text().count("::core::ffi::VaList") for path in rust_sources
            )
            if va_list_uses == 0 or any(
                "#![feature(c_variadic)]" in path.read_text() for path in rust_sources
            ):
                raise RuntimeError(
                    f"E2fsprogs missing c_variadic gate inventory changed for {args.program}"
                )
            changes.append(replace_once(
                staged / "lib.rs",
                "#![allow(deref_nullptr)]\n",
                "#![allow(deref_nullptr)]\n#![feature(c_variadic)]\n",
                "enable the nightly VaList ABI used by translated variadic wrappers",
            ))
        if args.program == "e2fsck":
            changes.append(replace_once(
                staged / "lib.rs",
                "pub mod r#super;\n",
                '#[path = "super.rs"]\n'
                "pub mod superblock;\n",
                "rename C super.c module because Rust reserves super even as a raw identifier",
            ))
        duplicate_exports_mangled = [
            *deduplicate_no_mangle_functions(staged),
            *deduplicate_no_mangle_statics(staged),
            *deduplicate_function_static_exports(staged),
        ]
        rust_sources = sorted(staged.rglob("*.rs"))
        hole_inventory = [
            str(path.relative_to(staged))
            for path in rust_sources if HOLE.search(path.read_text())
        ]
        if hole_inventory:
            raise RuntimeError(
                f"E2fsprogs translation holes remain for {args.program}: {hole_inventory}"
            )
        source_lines = sum(len(path.read_text().splitlines()) for path in rust_sources)
        raw_pointer_occurrences = sum(
            len(RAW_POINTER.findall(path.read_text())) for path in rust_sources
        )
        for change in changes:
            change["path"] = str(Path(change["path"]).relative_to(staged))
        manifest = {
            "schema": 1,
            "program": args.program,
            "toolchain": "nightly-2023-04-15",
            "repairs": len(changes),
            "files": len({change["path"] for change in changes}),
            "thread_local_feature_gates_preserved": feature_gates,
            "thread_local_attributes_preserved": attributes,
            "duplicate_exports_mangled": duplicate_exports_mangled,
            "rust_source_files": len(rust_sources),
            "rust_source_lines": source_lines,
            "raw_pointer_occurrences": raw_pointer_occurrences,
            "translation_holes": 0,
            "changes": changes,
        }
        (staged / "rustbox-e2fsprogs-finalization.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        if output.exists():
            shutil.rmtree(output)
        staged.rename(output)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    print(json.dumps({"program": args.program, "repairs": len(changes)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
