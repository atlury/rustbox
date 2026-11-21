#!/usr/bin/env python3
"""Publish deterministic GNU Gzip normalization and parity evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def suite_summary(path: Path) -> dict[str, int]:
    text = path.read_text(errors="replace")
    matches = list(re.finditer(
        r"# TOTAL:\s+(\d+).*?# PASS:\s+(\d+).*?# SKIP:\s+(\d+).*?"
        r"# XFAIL:\s+(\d+).*?# FAIL:\s+(\d+).*?# XPASS:\s+(\d+).*?# ERROR:\s+(\d+)",
        text,
        re.DOTALL,
    ))
    if not matches:
        raise RuntimeError(f"missing GNU Gzip test summary in {path}")
    return dict(zip(
        ("total", "pass", "skip", "xfail", "fail", "xpass", "error"),
        map(int, matches[-1].groups()),
    ))


def source_name(path: str) -> str:
    marker = "/rustbox-gzip/normalized-source/"
    if marker in path:
        return path.split(marker, 1)[1]
    if path.endswith("/version.c"):
        return "<generated>/version.c"
    raise RuntimeError(f"unexpected normalized compile source: {path}")


def needed(path: Path) -> list[str]:
    output = subprocess.run(
        ["readelf", "-d", str(path)], check=True, text=True, stdout=subprocess.PIPE
    ).stdout
    return re.findall(r"Shared library: \[([^]]+)\]", output)


def symbols(path: Path) -> set[str]:
    output = subprocess.run(
        ["nm", "-g", "--defined-only", str(path)], check=True, text=True,
        stdout=subprocess.PIPE,
    ).stdout
    return {line.split()[-1] for line in output.splitlines() if len(line.split()) >= 3}


def heap_summary(path: Path) -> str:
    text = path.read_text(errors="replace")
    match = re.search(
        r"total heap usage: [0-9,]+ allocs, [0-9,]+ frees, [0-9,]+ bytes allocated",
        text,
    )
    if (
        not match
        or "All heap blocks were freed -- no leaks are possible" not in text
        or "ERROR SUMMARY: 0 errors" not in text
    ):
        raise RuntimeError(f"incomplete GNU Gzip Valgrind result in {path}")
    return match.group(0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    base = repository / "work/analysis/gzip-1.14/normalized"
    oracle_base = repository / "work/analysis/gzip-1.14/oracle"
    oracle = json.loads((repository / "evidence/gzip-1.14-oracle.json").read_text())
    manifest_path = base / "normalization.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest["changed_sources"] != ["deflate.c", "gzip.c", "lib/vasnprintf.c"]:
        raise RuntimeError("GNU Gzip normalization source set changed")

    expected_suite = {
        "total": 30, "pass": 29, "skip": 1, "xfail": 0,
        "fail": 0, "xpass": 0, "error": 0,
    }
    canonical_sources = set(oracle["production_closure"]["sources"])
    portable_sources = canonical_sources - {"lib/crc-x86_64-pclmul.c"}
    compilers = {}
    closures = {}
    for compiler, expected_actions in (("gcc", 68), ("clang", 68), ("sanitizer", 71)):
        database_path = base / f"{compiler}-compile-commands.json"
        commands = json.loads(database_path.read_text())
        sources = sorted({source_name(record["file"]) for record in commands})
        if len(commands) != expected_actions or len(sources) != expected_actions:
            raise RuntimeError(f"normalized GNU Gzip {compiler} closure changed")
        expected_sources = set(portable_sources)
        if compiler == "sanitizer":
            expected_sources |= {"lib/fprintf.c", "lib/printf.c", "lib/vfprintf.c"}
        if set(sources) != expected_sources:
            raise RuntimeError(f"normalized GNU Gzip {compiler} sources changed")
        suite = suite_summary(base / f"{compiler}-check.log")
        if suite != expected_suite:
            raise RuntimeError(f"normalized GNU Gzip {compiler} tests changed: {suite}")
        closures[compiler] = sources
        compilers[compiler] = {
            "compile_actions": len(commands),
            "production_sources": len(sources),
            "compile_database_sha256": sha256(database_path),
            "upstream_suite": suite,
            "upstream_suite_log_sha256": sha256(base / f"{compiler}-check.log"),
        }

    differentials = {}
    for compiler in ("gcc", "clang"):
        path = base / f"canonical-normalized-{compiler}-differential.json"
        report = json.loads(path.read_text())
        if report.get("cases") != 54 or report.get("passed") != 54:
            raise RuntimeError(f"normalized GNU Gzip {compiler} differential changed")
        differentials[compiler] = {
            "comparisons": 54, "exact": True, "sha256": sha256(path),
        }

    binaries = {}
    for compiler in ("gcc", "clang"):
        binary = base / f"gzip-{compiler}"
        defined = symbols(binary)
        if not {"main", "rustbox_gzip_main"}.issubset(defined):
            raise RuntimeError(f"normalized GNU Gzip {compiler} entrypoints changed")
        libraries = needed(binary)
        if libraries != ["libc.so.6"]:
            raise RuntimeError(f"normalized GNU Gzip dependencies changed: {libraries}")
        with tempfile.TemporaryDirectory(prefix="rustbox-gzip-normalized-strip-") as temporary:
            stripped = Path(temporary) / "gzip"
            shutil.copy2(binary, stripped)
            subprocess.run(["strip", "--strip-all", str(stripped)], check=True)
            stripped_bytes = stripped.stat().st_size
            stripped_sha256 = sha256(stripped)
        binaries[compiler] = {
            "bytes": binary.stat().st_size,
            "sha256": sha256(binary),
            "stripped_bytes": stripped_bytes,
            "stripped_sha256": stripped_sha256,
            "needed": libraries,
            "entrypoints": ["main", "rustbox_gzip_main"],
        }

    resources = {}
    for operation in ("compress", "decompress"):
        normalized_path = base / f"valgrind-{operation}.log"
        normalized_summary = heap_summary(normalized_path)
        canonical_summary = heap_summary(oracle_base / f"valgrind-{operation}.log")
        if normalized_summary != canonical_summary:
            raise RuntimeError(f"normalized GNU Gzip {operation} resources changed")
        resources[operation] = {
            "matches_canonical_summary": True,
            "heap_summary": normalized_summary,
            "log_sha256": sha256(normalized_path),
        }

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-21",
        "release": "1.14",
        "normalization": manifest,
        "scope": {
            "canonical_production_sources": 69,
            "portable_production_sources": 68,
            "excluded_selected_optimization": "lib/crc-x86_64-pclmul.c",
            "portable_path_is_canonical_upstream_code": True,
            "compilers": compilers,
            "sources": closures,
        },
        "canonical_normalized_differential": {
            "comparisons": 108, "exact": True, "compilers": differentials,
        },
        "sanitizer": {
            "address": True,
            "undefined": True,
            "nonnull_attribute_enabled": True,
            "leak_detection_disabled_for_root_harness": True,
            "suite": expected_suite,
        },
        "resources": resources,
        "binaries": binaries,
        "manifest_sha256": sha256(manifest_path),
        "configuration": {
            "crc_pclmul": False,
            "crc_slice_by_8": True,
            "external_compression_library": False,
            "selinux": False,
            "systemd": False,
        },
        "next_gate": "translate the exact 68-source normalized GNU Gzip production closure with C2Rust",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "changed_sources": 3,
        "differential": 108,
        "portable_sources": 68,
        "upstream_passes": 29,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
