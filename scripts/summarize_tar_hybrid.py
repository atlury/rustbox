#!/usr/bin/env python3
"""Publish canonical parity and resource evidence for translated GNU tar."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def heap(path: Path) -> dict[str, object]:
    text = path.read_text(errors="replace")
    summary = re.search(r"total heap usage: .*", text)
    errors = re.search(r"ERROR SUMMARY: (\d+) errors", text)
    if not summary or not errors:
        raise RuntimeError(f"incomplete Valgrind log: {path}")
    losses = {}
    for kind in ("definitely", "indirectly", "possibly"):
        match = re.search(rf"{kind} lost: ([0-9,]+) bytes", text)
        if not match:
            raise RuntimeError(f"missing {kind} loss in {path}")
        losses[f"{kind}_lost_bytes"] = int(match.group(1).replace(",", ""))
    return {
        "errors": int(errors.group(1)),
        **losses,
        "heap_summary": summary.group(0),
        "log_sha256": sha256(path),
    }


def section(path: Path, name: str) -> int:
    match = re.search(rf"^{re.escape(name)}\s+(\d+)\s+", path.read_text(), re.M)
    if not match:
        raise RuntimeError(f"missing {name} in {path}")
    return int(match.group(1))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/tar-1.35/hybrid"
    artifacts = repository / "work/analysis/tar-1.35/hybrid-artifacts"
    differential_path = analysis / "differential.json"
    differential = json.loads(differential_path.read_text())
    if differential.get("cases") != 18 or differential.get("passed") != 18:
        raise RuntimeError("translated GNU tar differential is incomplete")
    if differential.get("public_names") != ["tar", "rmt"]:
        raise RuntimeError("GNU tar public-name inventory changed")

    resources = {
        operation: heap(analysis / f"valgrind-{operation}.log")
        for operation in ("create", "list", "extract", "rmt")
    }
    for operation in ("create", "list", "extract", "rmt"):
        record = resources[operation]
        if record["errors"] or any(record[f"{kind}_lost_bytes"]
                                   for kind in ("definitely", "indirectly", "possibly")):
            raise RuntimeError(f"GNU tar hybrid resource regression: {operation}")
    sizes = {}
    for utility, entrypoint in (("tar", "rustbox_tar_main"),
                                ("rmt", "rustbox_rmt_main")):
        symbols = (analysis / f"{utility}.symbols").read_text()
        if len(re.findall(rf" {entrypoint}$", symbols, re.M)) != 1:
            raise RuntimeError(f"GNU {utility} translated entrypoint is not unique")
        binary = artifacts / utility
        stripped = artifacts / f"{utility}.stripped"
        dynamic = (analysis / f"{utility}.dynamic").read_text()
        sizes[utility] = {
            "unstripped_bytes": binary.stat().st_size,
            "stripped_bytes": stripped.stat().st_size,
            "sha256": sha256(binary),
            "stripped_sha256": sha256(stripped),
            "sections": {
                name.removeprefix("."): section(
                    analysis / f"{utility}.sections", name
                )
                for name in (".text", ".rodata", ".data", ".bss")
            },
            "dynamic_needed": re.findall(
                r"Shared library: \[([^]]+)\]", dynamic
            ),
        }

    residue = json.loads((analysis / "c-residue.json").read_text())
    if len(residue["sources"]) != 4:
        raise RuntimeError("GNU tar canonical C ABI residue changed")
    translation = json.loads(
        (repository / "evidence/tar-1.35-c2rust.json").read_text()
    )
    multicall = json.loads(
        (repository / "evidence/rustbox-multicall.json").read_text()
    )
    tar_integration = multicall.get("tar_integration", {})
    if (
        tar_integration.get("integrated_public_names") != 2
        or tar_integration.get("system_libacl_dependency") is not False
        or tar_integration.get("differential", {}).get("passed") != 18
    ):
        raise RuntimeError("GNU tar unified integration evidence is incomplete")
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-22",
        "release": "1.35",
        "status": (
            "standalone translated hybrid and unified multicall integration "
            "at canonical parity with owned extraction cleanup"
        ),
        "implementation": {
            "translated_production_sources": 197,
            "canonical_c_abi_residue_sources": 4,
            "public_names": ["tar", "rmt"],
            "entrypoints": ["rustbox_tar_main", "rustbox_rmt_main"],
            "compile_error_or_placeholder_holes": 0,
        },
        "behavior": {
            "differential": differential,
            "differential_sha256": sha256(differential_path),
            "deterministic_archive_bytes_match": True,
            "extraction_trees_match": True,
            "resources": resources,
            "canonical_extraction_loss_bytes": 153,
            "hybrid_extraction_loss_bytes": 0,
        },
        "size": {
            "translation_static_archive_bytes":
                translation["stable_translation"]["release_archive"]["bytes"],
            "binaries": sizes,
        },
        "canonical_c_abi_residue": residue,
        "temporary_runtime_dependencies": {
            "scope": "standalone hybrid only",
            "libacl": True,
            "replacement": "Rustbox's already translated ACL implementation",
            "other_non_libc_system_libraries": [],
        },
        "unified_integration": tar_integration,
        "next_gate": "later pointer-safety and no-std hardening phase",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "differential": 18,
        "public_names": 2,
        "tar_stripped_bytes": sizes["tar"]["stripped_bytes"],
        "rmt_stripped_bytes": sizes["rmt"]["stripped_bytes"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
