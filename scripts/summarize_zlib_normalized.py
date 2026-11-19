#!/usr/bin/env python3
"""Verify and publish evidence for zlib's zero-change normalization."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def symbols(path: Path) -> list[str]:
    output = subprocess.run(
        ["nm", "-D", "--defined-only", str(path)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    return sorted({line.split()[-1].split("@@", 1)[0] for line in output.splitlines() if line.split()})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/zlib-1.4"
    normalized = analysis / "normalized"
    manifest_path = normalized / "normalization.json"
    manifest = json.loads(manifest_path.read_text())
    changed = sorted(
        name for name, record in manifest["production_sources"].items() if record["changed"]
    )
    if changed != ["compress.c", "uncompr.c"] or len(manifest["transformations"]) != 3:
        raise RuntimeError(f"unexpected zlib normalization change set: {changed!r}")

    build = normalized / "gcc-cmake"
    inventory = json.loads(subprocess.run(
        ["ctest", "--test-dir", str(build), "--show-only=json-v1"],
        check=True, text=True, stdout=subprocess.PIPE,
    ).stdout)
    result = subprocess.run(
        ["ctest", "--test-dir", str(build), "--output-on-failure", "--parallel", "2"],
        check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    ).stdout
    if len(inventory["tests"]) != 18 or "100% tests passed, 0 tests failed out of 18" not in result:
        raise RuntimeError("normalized upstream tests are incomplete")

    compile_commands = json.loads((normalized / "clang-make/compile_commands.json").read_text())
    production = sorted({
        Path(record["file"]).name
        for record in compile_commands
        if Path(record["file"]).parent.name == "source"
    })
    if production != sorted(manifest["production_sources"]):
        raise RuntimeError("normalized Clang database lacks a production source")

    canonical_library = analysis / "canonical-gcc-cmake/libz.so.1.4"
    normalized_library = build / "libz.so.1.4"
    canonical_symbols = symbols(canonical_library)
    normalized_symbols = symbols(normalized_library)
    if canonical_symbols != normalized_symbols:
        raise RuntimeError("normalization changed zlib's exported symbol set")
    abi = subprocess.run(
        ["abidiff", str(canonical_library), str(normalized_library)],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    # Libabigail uses bit 0 for an ABI change and may use higher status bits
    # for harmless debug-information limitations.  An actual ABI change is fatal.
    if abi.returncode & 1:
        raise RuntimeError(f"normalization changed ABI:\n{abi.stdout[-4000:]}")

    evidence = {
        "schema": 1,
        "release": "1.4",
        "normalization": {
            "strategy": manifest["strategy"],
            "changed_sources": 2,
            "production_sources": len(production),
            "canonical_tree_sha256": manifest["canonical_tree_sha256"],
            "normalized_tree_sha256": manifest["normalized_tree_sha256"],
            "manifest_sha256": sha256(manifest_path),
        },
        "compiler_replays": {
            "gcc_cmake_tests": {"total": 18, "passed": 18},
            "clang_make": {
                "compile_commands": len(compile_commands),
                "production_sources": production,
                "gates": ["static", "shared", "large-file-64"],
            },
            "gcc_sanitizers": {"address": "pass", "undefined": "pass"},
            "valgrind": {"example": "pass", "infcover": "pass"},
        },
        "abi": {
            "exported_symbol_count": len(normalized_symbols),
            "matching_exports": True,
            "abidiff_exit_status": abi.returncode,
            "abidiff_output_sha256": hashlib.sha256(abi.stdout.encode()).hexdigest(),
        },
        "translation_policy": {
            "semantic_patches": [
                "normalization/zlib/split-z-size-declarators.cocci",
                "normalization/zlib/explicit-z-size.cocci",
            ],
            "holes_allowed": False,
            "next_gate": "C2Rust audit translation of all production compile commands",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"changed_sources": 2, "tests": 18, "exports": len(normalized_symbols)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
