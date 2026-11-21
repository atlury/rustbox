#!/usr/bin/env python3
"""Summarize deterministic GNU bc normalization and parity gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def needed(path: Path) -> list[str]:
    output = subprocess.run(
        ["readelf", "-d", str(path)], check=True, text=True, stdout=subprocess.PIPE
    ).stdout
    return re.findall(r"Shared library: \[([^]]+)\]", output)


def global_symbols(path: Path) -> dict[str, str]:
    output = subprocess.run(
        ["nm", "-g", str(path)], check=True, text=True, stdout=subprocess.PIPE
    ).stdout
    symbols: dict[str, str] = {}
    for line in output.splitlines():
        fields = line.split()
        if len(fields) == 3:
            symbols[fields[2]] = fields[1]
    return symbols


def source_closure(database: Path) -> tuple[list[str], int]:
    records = json.loads(database.read_text())
    prefix = "/rustbox-bc/normalized-source/"
    paths = [str(record["file"]) for record in records]
    if any(not path.startswith(prefix) for path in paths):
        raise RuntimeError("normalized GNU bc source escaped expected prefix")
    sources = sorted({path.removeprefix(prefix) for path in paths})
    return sources, len(records)


def test_names(path: Path) -> list[str]:
    names = []
    for line in path.read_text().splitlines():
        match = re.fullmatch(r"(\S+) pass", line)
        if not match:
            raise RuntimeError(f"unexpected normalized GNU bc test record: {line!r}")
        names.append(match.group(1))
    return names


def valgrind_summary(path: Path) -> dict[str, int]:
    text = path.read_text(errors="replace")
    heap = re.search(
        r"in use at exit: ([0-9,]+) bytes in ([0-9,]+) blocks.*?"
        r"total heap usage: ([0-9,]+) allocs, ([0-9,]+) frees, ([0-9,]+) bytes allocated",
        text,
        re.DOTALL,
    )
    if not heap or "ERROR SUMMARY: 0 errors" not in text:
        raise RuntimeError(f"normalized GNU bc Valgrind summary changed: {path}")
    values = [int(value.replace(",", "")) for value in heap.groups()]
    return {
        "bytes_at_exit": values[0], "blocks_at_exit": values[1],
        "allocations": values[2], "frees": values[3], "bytes_allocated": values[4],
        "errors": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    base = repository / "work/analysis/bc-1.08.2/normalized"
    oracle = json.loads((repository / "evidence/bc-1.08.2-oracle.json").read_text())
    manifest_path = base / "normalization.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest["changed_sources"] != ["bc/main.c", "dc/dc.c"]:
        raise RuntimeError("GNU bc normalization manifest changed")

    source_sets: dict[str, list[str]] = {}
    actions: dict[str, int] = {}
    database_hashes: dict[str, str] = {}
    for compiler in ("gcc", "clang", "sanitizer"):
        database = base / f"{compiler}-compile-commands.json"
        source_sets[compiler], actions[compiler] = source_closure(database)
        database_hashes[compiler] = sha256(database)
    if any(sources != source_sets["gcc"] for sources in source_sets.values()):
        raise RuntimeError("normalized GNU bc compiler source closures differ")
    if source_sets["gcc"] != oracle["scope"]["production_sources"]:
        raise RuntimeError("normalized GNU bc closure differs from canonical oracle")

    tests = {
        compiler: test_names(base / f"{compiler}-upstream-tests.log")
        for compiler in ("gcc", "clang", "sanitizer")
    }
    for compiler in tests:
        if tests[compiler] != oracle["tests"][compiler]["shipped_case_names"]:
            raise RuntimeError(f"normalized GNU bc {compiler} shipped-test coverage changed")

    differentials = {}
    for compiler in ("gcc", "clang"):
        path = base / f"canonical-normalized-{compiler}-differential.json"
        report = json.loads(path.read_text())
        if report.get("cases") != 46 or report.get("passed") != 46:
            raise RuntimeError(f"GNU bc normalized {compiler} differential changed")
        differentials[compiler] = {"comparisons": 46, "exact": True, "sha256": sha256(path)}

    binaries: dict[str, dict[str, object]] = {}
    objects: dict[str, dict[str, object]] = {}
    for compiler in ("gcc", "clang"):
        binaries[compiler] = {}
        objects[compiler] = {}
        for applet, object_prefix, entrypoint in (
            ("bc", "bc-main", "rustbox_bc_main"),
            ("dc", "dc-main", "rustbox_dc_main"),
        ):
            binary = base / f"{applet}-{compiler}"
            dependencies = needed(binary)
            if dependencies != ["libc.so.6"]:
                raise RuntimeError(f"normalized GNU {applet} dependencies changed: {dependencies}")
            object_path = base / f"{object_prefix}-{compiler}.o"
            symbols = global_symbols(object_path)
            if symbols.get("main") not in ("T", "t") or symbols.get(entrypoint) not in ("T", "t"):
                raise RuntimeError(f"normalized GNU {applet} entrypoint symbols changed")
            binaries[compiler][applet] = {
                "bytes": binary.stat().st_size,
                "sha256": sha256(binary),
                "needed": dependencies,
            }
            objects[compiler][applet] = {
                "sha256": sha256(object_path),
                "entrypoints": ["main", entrypoint],
            }

    resources = {}
    for applet in ("bc", "dc"):
        summary = valgrind_summary(base / f"valgrind-{applet}.log")
        canonical = {key: value for key, value in oracle["valgrind"][applet].items()
                     if key != "log_sha256"}
        if summary != canonical:
            raise RuntimeError(f"normalized GNU {applet} resource baseline changed")
        resources[applet] = {
            "matches_canonical_summary": True,
            "summary": summary,
            "log_sha256": sha256(base / f"valgrind-{applet}.log"),
        }

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-21",
        "release": "1.08.2",
        "bundled_dc_release": "1.5.2",
        "normalization": manifest,
        "scope": {
            "production_sources": len(source_sets["gcc"]),
            "captured_compile_actions": actions,
            "source_closure_matches_canonical": True,
            "compile_database_sha256": database_hashes,
        },
        "tests": {
            compiler: {
                "shipped_cases": len(names),
                "canonical_outputs_exact": True,
                "log_sha256": sha256(base / f"{compiler}-upstream-tests.log"),
                "automake_check_log_sha256": sha256(base / f"{compiler}-check.log"),
            }
            for compiler, names in tests.items()
        },
        "canonical_normalized_differential": {
            "comparisons": 92,
            "exact": True,
            "compilers": differentials,
        },
        "valgrind": resources,
        "binaries": binaries,
        "entrypoint_objects": objects,
        "manifest_sha256": sha256(manifest_path),
        "next_gate": "translate the exact 21-source normalized production closure with C2Rust",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"changed_sources": 2, "differential": 92, "production_sources": 21}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
