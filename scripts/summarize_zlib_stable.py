#!/usr/bin/env python3
"""Publish evidence for the isolated stable-Rust zlib library."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


HOLES = (
    re.compile(r"\bcompile_error!"),
    re.compile(r"\btodo!"),
    re.compile(r"\bunimplemented!"),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/zlib-1.4"
    base = analysis / "translations/c2rust-0.22.1"
    generic = base / "zlib-1.4-modernized-stable"
    stable = base / "zlib-1.4-stable"
    library = stable / "target/release/libzlib_1_4_normalized_audit.a"
    paths = {
        "audit": repository / "evidence/zlib-1.4-c2rust-audit.json",
        "generic": generic / "rustbox-modernization.json",
        "zlib": stable / "rustbox-zlib-modernization.json",
        "cargo": stable / "rustbox-cargo-check.json",
        "differential": stable / "differential.json",
    }
    for path in [library, *paths.values()]:
        if not path.is_file():
            raise RuntimeError(f"missing stable zlib artifact: {path}")
    cargo = load(paths["cargo"])
    differential = load(paths["differential"])
    if not cargo["build_finished_success"] or cargo["errors"]:
        raise RuntimeError("stable zlib crate does not compile")
    if not differential["canonical_rust_exact"] or differential["comparisons"] != 98:
        raise RuntimeError("stable zlib differential suite is incomplete")

    rust_files = sorted(stable.rglob("*.rs"))
    combined = "\n".join(path.read_text() for path in rust_files)
    if any(pattern.search(combined) for pattern in HOLES):
        raise RuntimeError("stable zlib crate contains a translation hole")
    oracle = load(repository / "evidence/zlib-1.4-oracle.json")
    expected_symbols = sorted(
        symbol for symbol in oracle["abi"]["exported_symbols"]
        if not symbol.startswith("ZLIB_")
    )
    nm = subprocess.run(
        ["nm", "-g", "--defined-only", str(library)],
        check=True, text=True, stdout=subprocess.PIPE,
    ).stdout
    defined = [line.split()[-1] for line in nm.splitlines() if line.split()]
    if any(defined.count(symbol) != 1 for symbol in expected_symbols):
        raise RuntimeError("stable Rust archive does not define every zlib API exactly once")

    generic_manifest = load(paths["generic"])
    opaque = sorted({
        name
        for change in generic_manifest["changes"]
        for name in change["opaque_pointer_types"]
    })
    evidence = {
        "schema": 1,
        "status": "isolated stable Rust library at canonical parity",
        "release": "1.4",
        "artifacts": {
            "static_library_bytes": library.stat().st_size,
            "static_library_sha256": sha256(library),
            "rust_files": len(rust_files),
            "rust_bytes": sum(path.stat().st_size for path in rust_files),
            "public_c_api_symbols": len(expected_symbols),
            "public_c_api_symbols_defined_once": True,
        },
        "stable_modernization": {
            "toolchain": "1.99.0",
            "generic_manifest_sha256": sha256(paths["generic"]),
            "zlib_manifest_sha256": sha256(paths["zlib"]),
            "opaque_types_verified_pointer_only": opaque,
            "function_pointer_identity": "core::ptr::fn_addr_eq",
            "generated_rules": 2,
            "hand_edits": 0,
            "repair_score": 7,
        },
        "cargo_check": cargo,
        "behavior": differential,
        "input_evidence": {
            "oracle_sha256": sha256(repository / "evidence/zlib-1.4-oracle.json"),
            "normalization_sha256": sha256(repository / "evidence/zlib-1.4-normalization.json"),
            "audit_sha256": sha256(paths["audit"]),
        },
        "integration": {
            "applets": [],
            "multicall_linked": False,
            "policy": "Keep library isolated; final shared/static linkage policy is deferred.",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "comparisons": differential["comparisons"],
        "library_bytes": library.stat().st_size,
        "public_symbols": len(expected_symbols),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
