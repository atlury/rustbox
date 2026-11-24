#!/usr/bin/env python3
"""Publish strict no-hole IPRoute2 translation and compile evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rust_inventory(root: Path) -> tuple[list[Path], int, int, int]:
    files = sorted(root.rglob("*.rs"))
    lines = raw_pointers = unsafe_tokens = 0
    for path in files:
        text = path.read_text()
        lines += len(text.splitlines())
        raw_pointers += len(re.findall(r"\*(?:mut|const) ", text))
        unsafe_tokens += len(re.findall(r"\bunsafe\b", text))
        if "unimplemented!(" in text or "todo!(" in text:
            raise RuntimeError(f"IPRoute2 translation hole in {path}")
    return files, lines, raw_pointers, unsafe_tokens


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.repository.resolve()
    base = root / "work/analysis/iproute2-7.3.0"
    translation = base / "translations/c2rust-0.22.1"
    audit = translation / "iproute2-7.3.0-normalized-audit"
    stable = translation / "iproute2-7.3.0-normalized-stable"
    final = translation / "iproute2-7.3.0-normalized-final"

    closure_path = base / "c2rust-compdb/closure.json"
    closure = json.loads(closure_path.read_text())
    if (
        closure.get("commands") != 260
        or closure.get("duplicate_actions_collapsed") != 4
        or len(closure.get("excluded_build_helpers", [])) != 4
    ):
        raise RuntimeError("IPRoute2 strict translation closure changed")

    files, lines, raw_pointers, unsafe_tokens = rust_inventory(audit)
    entrypoints = set()
    for path in files:
        entrypoints.update(re.findall(r"rustbox_iproute2_([a-z0-9_]+)_main", path.read_text()))
    if len(files) != 262 or lines != 637495 or len(entrypoints) != 18:
        raise RuntimeError(
            f"IPRoute2 generated inventory changed: files={len(files)}, "
            f"lines={lines}, entrypoints={sorted(entrypoints)}"
        )

    checks = {}
    for name in ("audit", "stable", "final"):
        path = translation / f"{name}-cargo-check.json"
        result = json.loads(path.read_text())
        checks[name] = {
            "exit_status": result["exit_status"],
            "errors": len(result["errors"]),
            "rustc": result["rustc"],
            "sha256": sha256(path),
        }
    if checks["audit"]["errors"] != 10 or checks["audit"]["exit_status"] != 101:
        raise RuntimeError("IPRoute2 raw audit diagnostics changed")
    # check_cargo_crate records rustc's final abort note as an error only on
    # the pinned nightly; both pre-finalization crates have nine type errors.
    if checks["stable"]["errors"] != 9 or checks["stable"]["exit_status"] != 101:
        raise RuntimeError("IPRoute2 modernized diagnostics changed")
    if checks["final"]["errors"] != 0 or checks["final"]["exit_status"] != 0:
        raise RuntimeError("IPRoute2 finalized crate does not type-check")

    modernization_path = stable / "rustbox-modernization.json"
    modernization = json.loads(modernization_path.read_text())
    asm_repairs = sum(
        change.get("asm_cast_mutable_borrow_rewrites", 0)
        for change in modernization["changes"]
    )
    duplicate_exports = modernization.get("duplicate_exports_mangled", [])
    if asm_repairs != 180 or len(duplicate_exports) != 59:
        raise RuntimeError("IPRoute2 mechanical modernization inventory changed")
    finalization_path = final / "rustbox-iproute2-finalization.json"
    finalization = json.loads(finalization_path.read_text())
    if finalization.get("repairs") != 10 or finalization.get("files") != 7:
        raise RuntimeError("IPRoute2 asserted finalization inventory changed")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-24",
        "release": "7.3.0",
        "status": "complete strict no-hole translation and latest-stable compile audit",
        "source_closure": {
            "production_sources": 260,
            "duplicate_actions_collapsed": 4,
            "excluded_build_helpers": closure["excluded_build_helpers"],
            "compile_database_sha256": closure["sha256"],
            "manifest_sha256": sha256(closure_path),
        },
        "generated": {
            "rust_files": len(files),
            "rust_lines": lines,
            "entrypoints": sorted(entrypoints),
            "translation_holes": 0,
            "raw_pointer_type_occurrences": raw_pointers,
            "unsafe_token_occurrences": unsafe_tokens,
        },
        "compile_checks": checks,
        "modernization": {
            "files_changed": len(modernization["changes"]),
            "asm_cast_mutable_borrow_rewrites": asm_repairs,
            "monolithic_duplicate_exports_mangled": len(duplicate_exports),
            "manifest_sha256": sha256(modernization_path),
        },
        "asserted_repairs": {
            "repairs": 10,
            "files": 7,
            "manifest_sha256": sha256(finalization_path),
        },
        "runtime_policy": {
            "monolithic_crate_is_audit_only": True,
            "reason": "formerly separate programs contain colliding mutable C globals",
            "next_gate": "18 exact linker-map program closures and hybrid canonical parity",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "sources": 260,
        "rust_files": len(files),
        "repairs": 10,
        "raw_pointers": raw_pointers,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
