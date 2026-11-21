#!/usr/bin/env python3
"""Publish deterministic attr normalization and parity evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_summary(path: Path) -> dict[str, int]:
    text = path.read_text(errors="replace")
    result = {}
    for name in ("TOTAL", "PASS", "SKIP", "XFAIL", "FAIL", "XPASS", "ERROR"):
        match = re.search(rf"^# {name}:\s+(\d+)$", text, re.MULTILINE)
        if not match:
            raise RuntimeError(f"missing {name} in {path}")
        result[name.lower()] = int(match.group(1))
    expected = {"total": 3, "pass": 2, "skip": 1, "xfail": 0, "fail": 0, "xpass": 0, "error": 0}
    if result != expected:
        raise RuntimeError(f"normalized attr upstream test summary changed: {result}")
    return result


def symbols(path: Path) -> set[str]:
    output = subprocess.run(
        ["nm", "-g", "--defined-only", str(path)], check=True, text=True,
        stdout=subprocess.PIPE,
    ).stdout
    return {line.split()[-1] for line in output.splitlines() if len(line.split()) >= 3}


def needed(path: Path) -> list[str]:
    output = subprocess.run(
        ["readelf", "-d", str(path)], check=True, text=True, stdout=subprocess.PIPE
    ).stdout
    return re.findall(r"Shared library: \[([^]]+)\]", output)


def heap_summary(path: Path) -> list[str]:
    text = path.read_text(errors="replace")
    lines = []
    for pattern in (
        r"in use at exit: [0-9,]+ bytes in [0-9,]+ blocks",
        r"total heap usage: [0-9,]+ allocs, [0-9,]+ frees, [0-9,]+ bytes allocated",
        r"still reachable: [0-9,]+ bytes in [0-9,]+ blocks",
    ):
        match = re.search(pattern, text)
        if not match:
            raise RuntimeError(f"missing Valgrind heap line in {path}")
        lines.append(match.group(0))
    for phrase in (
        "definitely lost: 0 bytes in 0 blocks",
        "indirectly lost: 0 bytes in 0 blocks",
        "possibly lost: 0 bytes in 0 blocks",
        "ERROR SUMMARY: 0 errors",
    ):
        if phrase not in text:
            raise RuntimeError(f"incomplete Valgrind result in {path}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    base = repository / "work/analysis/attr-2.6.0/normalized"
    oracle_dir = repository / "work/analysis/attr-2.6.0/oracle"
    oracle = json.loads((repository / "evidence/attr-2.6.0-oracle.json").read_text())
    manifest_path = base / "normalization.json"
    manifest = json.loads(manifest_path.read_text())
    expected_changed = ["tools/attr.c", "tools/getfattr.c", "tools/setfattr.c"]
    if manifest["changed_sources"] != expected_changed:
        raise RuntimeError("attr normalization source set changed")

    compilers = {}
    source_sets = []
    for compiler in ("gcc", "clang", "sanitizer"):
        database = base / f"{compiler}-compile-commands.json"
        commands = json.loads(database.read_text())
        prefix = "/rustbox-attr/normalized-source/"
        sources = sorted({record["file"].removeprefix(prefix) for record in commands})
        if len(commands) != 21 or any(not record["file"].startswith(prefix) for record in commands):
            raise RuntimeError(f"normalized attr {compiler} compilation closure changed")
        source_sets.append(sources)
        compilers[compiler] = {
            "compile_actions": len(commands),
            "compile_database_sha256": sha256(database),
            "upstream_tests": test_summary(base / f"{compiler}-check.log"),
            "test_log_sha256": sha256(base / f"{compiler}-check.log"),
        }
    if any(sources != source_sets[0] for sources in source_sets[1:]):
        raise RuntimeError("normalized attr compiler source closures differ")
    if source_sets[0] != oracle["scope"]["production_sources"]:
        raise RuntimeError("normalized attr closure differs from canonical oracle")

    differentials = {}
    for compiler in ("gcc", "clang"):
        path = base / f"canonical-normalized-{compiler}-differential.json"
        report = json.loads(path.read_text())
        if report.get("cases") != 22 or report.get("passed") != 22:
            raise RuntimeError(f"normalized attr {compiler} differential changed")
        differentials[compiler] = {"comparisons": 22, "exact": True, "sha256": sha256(path)}

    entrypoints = {
        "attr": "rustbox_attr_main",
        "getfattr": "rustbox_getfattr_main",
        "setfattr": "rustbox_setfattr_main",
    }
    binaries = {}
    objects = {}
    for compiler in ("gcc", "clang"):
        binaries[compiler] = {}
        objects[compiler] = {}
        for applet, entrypoint in entrypoints.items():
            binary = base / f"{applet}-{compiler}"
            libraries = needed(binary)
            if libraries != ["libc.so.6"]:
                raise RuntimeError(f"normalized attr dependency set changed: {libraries}")
            object_path = base / f"{applet}-{compiler}.o"
            defined = symbols(object_path)
            if not {"main", entrypoint}.issubset(defined):
                raise RuntimeError(f"normalized attr {applet} entrypoints changed")
            binaries[compiler][applet] = {
                "bytes": binary.stat().st_size, "sha256": sha256(binary), "needed": libraries,
            }
            objects[compiler][applet] = {
                "sha256": sha256(object_path), "entrypoints": ["main", entrypoint],
            }

    resources = {}
    for applet in ("setfattr", "getfattr"):
        normalized_summary = heap_summary(base / f"valgrind-{applet}.log")
        canonical_summary = heap_summary(oracle_dir / f"valgrind-{applet}.log")
        if normalized_summary != canonical_summary:
            raise RuntimeError(f"normalized attr {applet} resource summary differs from canonical")
        resources[applet] = {
            "matches_canonical_summary": True,
            "heap_summary": normalized_summary,
            "log_sha256": sha256(base / f"valgrind-{applet}.log"),
        }

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-21",
        "release": "2.6.0",
        "normalization": manifest,
        "scope": {
            "production_sources": 21,
            "source_closure_matches_canonical": True,
            "compilers": compilers,
        },
        "canonical_normalized_differential": {
            "comparisons": 44, "exact": True, "compilers": differentials,
        },
        "resources": resources,
        "binaries": binaries,
        "entrypoint_objects": objects,
        "manifest_sha256": sha256(manifest_path),
        "configuration": {"nls": False, "selinux": False, "systemd": False},
        "next_gate": "translate the exact 21-source normalized attr production closure with C2Rust",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"changed_sources": 3, "differential": 44, "production_sources": 21}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
