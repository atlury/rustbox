#!/usr/bin/env python3
"""Generate evidence for deterministic zstd 1.5.7 normalization."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


EXPECTED_CLOSURE_SHA256 = "23c71282b9622802be36fdf7109b3542885e8f9a0b34734005ec6834d9821a2a"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def needed(path: Path) -> list[str]:
    output = subprocess.run(
        ["readelf", "-d", str(path)], check=True, text=True, stdout=subprocess.PIPE
    ).stdout
    return re.findall(r"Shared library: \[([^]]+)\]", output)


def source_names(database: Path, compiler: str) -> tuple[int, list[str]]:
    records = json.loads(database.read_text())
    marker = f"/normalized-{compiler}/"
    names = sorted({record["file"].replace("\\", "/").split(marker, 1)[1]
                    for record in records})
    return len(records), names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    normalized = repository / "work/analysis/zstd-1.5.7/normalized"
    manifest_path = normalized / "normalization.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest["changed_sources"] != ["programs/zstdcli.c"] or manifest["entrypoints"] != 1:
        raise RuntimeError("zstd normalization manifest changed")

    compilers: dict[str, object] = {}
    production_sources: list[str] | None = None
    for compiler in ("gcc", "clang", "sanitizer"):
        database = normalized / f"{compiler}-compile-commands.json"
        actions, sources = source_names(database, compiler)
        closure = hashlib.sha256(("\n".join(sources) + "\n").encode()).hexdigest()
        if actions != 44 or len(sources) != 44 or closure != EXPECTED_CLOSURE_SHA256:
            raise RuntimeError(f"normalized zstd {compiler} closure changed")
        if production_sources is None:
            production_sources = sources
        elif sources != production_sources:
            raise RuntimeError("normalized zstd compiler closures differ")
        log = normalized / f"{compiler}-check.log"
        text = log.read_text(errors="replace")
        if "All tests completed successfully" not in text:
            raise RuntimeError(f"normalized zstd {compiler} suite is incomplete")
        if compiler == "sanitizer" and (
            "ERROR: AddressSanitizer" in text
            or re.search(r"\.c:\d+(?::\d+)?: runtime error:", text)
        ):
            raise RuntimeError("normalized zstd sanitizer suite reported a defect")
        compilers[compiler] = {
            "compile_actions": actions, "production_sources": len(sources),
            "compile_database_sha256": sha256(database),
            "upstream_tests": "complete upstream make check",
            "upstream_test_log_sha256": sha256(log), "passed": True,
        }
    assert production_sources is not None

    differentials: dict[str, object] = {}
    for compiler in ("gcc", "clang"):
        path = normalized / f"canonical-normalized-{compiler}-differential.json"
        value = json.loads(path.read_text())
        if value.get("cases") != 17 or value.get("passed") != 17:
            raise RuntimeError(f"normalized zstd {compiler} differential is incomplete")
        differentials[compiler] = {"cases": 17, "passed": 17, "sha256": sha256(path)}

    binaries: dict[str, object] = {}
    for compiler in ("gcc", "clang"):
        binary = normalized / f"{compiler}-root/usr/bin/zstd"
        with tempfile.TemporaryDirectory(prefix="rustbox-zstd-normalized-strip-") as temporary:
            stripped = Path(temporary) / "zstd"
            shutil.copy2(binary, stripped)
            subprocess.run(["strip", "--strip-all", str(stripped)], check=True)
            stripped_bytes = stripped.stat().st_size
            stripped_digest = sha256(stripped)
        dependencies = needed(binary)
        if dependencies != ["libc.so.6"]:
            raise RuntimeError(f"normalized zstd {compiler} dependencies changed: {dependencies}")
        binaries[compiler] = {
            "bytes": binary.stat().st_size, "sha256": sha256(binary),
            "stripped_bytes": stripped_bytes, "stripped_sha256": stripped_digest,
            "dynamic_needed": dependencies,
        }

    evidence = {
        "schema": 1, "recorded_at": "2026-11-22", "release": "1.5.7",
        "status": "complete deterministic normalization; C2Rust translation pending",
        "manifest": manifest,
        "manifest_sha256": sha256(manifest_path),
        "production_sources": production_sources,
        "production_source_count": len(production_sources),
        "production_closure_sha256": EXPECTED_CLOSURE_SHA256,
        "compilers": compilers,
        "canonical_normalized_differential": differentials,
        "binaries": binaries,
        "review": {
            "canonical_source_files_changed": 1,
            "algorithm_changes": 0,
            "portable_substitution": "upstream ZSTD_NO_ASM=1 C implementation replaces optional x86-64 Huffman assembly",
            "entrypoint": "rustbox_zstd_main with conditional standalone wrapper",
            "all_six_public_names_retained": True,
            "external_runtime_libraries": [],
        },
        "next_gate": "translate all 44 portable production C units with C2Rust and repair mechanically without holes",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"changed_sources": 1, "differential": 34,
                      "production_sources": 44, "upstream_suites": 3}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
