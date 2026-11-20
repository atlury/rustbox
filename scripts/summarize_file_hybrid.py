#!/usr/bin/env python3
"""Publish canonical-parity and size evidence for translated File."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def section(path: Path, name: str) -> int:
    match = re.search(rf"^{re.escape(name)}\s+(\d+)\s+", path.read_text(), re.MULTILINE)
    if not match:
        raise RuntimeError(f"missing {name} in {path}")
    return int(match.group(1))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/file-5.48/hybrid"
    build = repository / "build/file-5.48-hybrid"
    binary = build / "file-hybrid"
    stripped = build / "file-hybrid.stripped"
    canonical = build / "file.canonical-stripped"

    upstream_path = analysis / "upstream-tests.log"
    upstream = upstream_path.read_text(errors="replace")
    fixtures = len(re.findall(r"^Running test:", upstream, re.MULTILINE))
    if fixtures != 83:
        raise RuntimeError("translated File upstream fixture suite changed")

    differential_path = analysis / "differential.json"
    differential = json.loads(differential_path.read_text())
    if not differential["gcc_clang_exact"] or differential["comparisons"] != 174:
        raise RuntimeError("translated File differential suite is incomplete")

    valgrind_path = analysis / "valgrind-cli.log"
    valgrind = valgrind_path.read_text(errors="replace")
    if (
        "ERROR SUMMARY: 0 errors" not in valgrind
        or "All heap blocks were freed -- no leaks are possible" not in valgrind
    ):
        raise RuntimeError("File hybrid Valgrind smoke failed")

    dynamic = (build / "file-hybrid.dynamic").read_text()
    needed = re.findall(r"Shared library: \[([^]]+)\]", dynamic)
    expected_needed = [
        "libbz2.so.1.0", "liblz.so.1", "liblzma.so.5", "libseccomp.so.2",
        "libz.so.1", "libzstd.so.1", "libm.so.6", "libgcc_s.so.1",
        "libc.so.6", "ld-linux-x86-64.so.2",
    ]
    if needed != expected_needed:
        raise RuntimeError(f"unexpected File hybrid runtime dependencies: {needed!r}")

    translation = json.loads((repository / "evidence/file-5.48-c2rust.json").read_text())
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-20",
        "release": "5.48",
        "status": "complete translated hybrid at canonical parity; multicall integration pending",
        "implementation": {
            "rust_production_sources": 25,
            "rust_files": translation["stable_translation"]["rust_files"],
            "entrypoint": "rustbox_file_main",
            "public_name": "file",
        },
        "behavior": {
            "upstream_libmagic_fixtures_relinked_against_rust": fixtures,
            "differential": differential,
            "valgrind_smokes": 1,
        },
        "size": {
            "translation_static_archive_bytes": translation["stable_translation"]["archive"]["bytes"],
            "linked_unstripped_bytes": binary.stat().st_size,
            "linked_stripped_bytes": stripped.stat().st_size,
            "canonical_stripped_bytes": canonical.stat().st_size,
            "linked_sections": {
                name.removeprefix("."): section(build / "file-hybrid.sections", name)
                for name in (".text", ".rodata", ".data", ".bss")
            },
            "interpretation": "The static archive is link inventory, not release size.",
        },
        "artifacts": {
            "linked_sha256": sha256(binary),
            "stripped_sha256": sha256(stripped),
            "upstream_log_sha256": sha256(upstream_path),
            "differential_sha256": sha256(differential_path),
            "valgrind_log_sha256": sha256(valgrind_path),
        },
        "runtime_linkage": {
            "current_dynamic_needed": needed,
            "compression_and_sandbox_backends": [
                "bzip2", "lzip", "xz", "seccomp", "zlib", "zstd"
            ],
            "final_no_dt_needed_gate": "pending Rustbox-owned static runtime and backends",
        },
        "input_evidence": {
            name: sha256(repository / f"evidence/{name}")
            for name in (
                "file-5.48-oracle.json",
                "file-5.48-normalization.json",
                "file-5.48-c2rust.json",
            )
        },
        "next_gate": "link file into the single Rustbox multicall and replay combined regressions",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "differential": differential["comparisons"],
        "fixtures": fixtures,
        "stripped_bytes": stripped.stat().st_size,
        "text_bytes": evidence["size"]["linked_sections"]["text"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
