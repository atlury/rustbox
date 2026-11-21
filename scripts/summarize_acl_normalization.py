#!/usr/bin/env python3
"""Publish deterministic acl normalization and parity evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_summary(path: Path, expected: dict[str, int]) -> dict[str, int]:
    text = path.read_text(errors="replace")
    result = {}
    for name in ("TOTAL", "PASS", "SKIP", "XFAIL", "FAIL", "XPASS", "ERROR"):
        match = re.search(rf"^# {name}:\s+(\d+)$", text, re.MULTILINE)
        if not match:
            raise RuntimeError(f"missing {name} in {path}")
        result[name.lower()] = int(match.group(1))
    if result != expected:
        raise RuntimeError(f"normalized acl test summary changed in {path}: {result}")
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


def heap_summary(path: Path) -> str:
    text = path.read_text(errors="replace")
    match = re.search(
        r"total heap usage: [0-9,]+ allocs, [0-9,]+ frees, [0-9,]+ bytes allocated",
        text,
    )
    for phrase in (
        "All heap blocks were freed -- no leaks are possible",
        "ERROR SUMMARY: 0 errors",
    ):
        if phrase not in text:
            raise RuntimeError(f"incomplete Valgrind result in {path}")
    if not match:
        raise RuntimeError(f"missing Valgrind heap line in {path}")
    return match.group(0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    base = repository / "work/analysis/acl-2.4.0/normalized"
    oracle_dir = repository / "work/analysis/acl-2.4.0/oracle"
    oracle = json.loads((repository / "evidence/acl-2.4.0-oracle.json").read_text())
    manifest_path = base / "normalization.json"
    manifest = json.loads(manifest_path.read_text())
    expected_changed = [
        "libacl/__libobj.c", "libacl/acl_free.c", "tools/chacl.c",
        "tools/do_set.c", "tools/do_set.h", "tools/getfacl.c",
        "tools/setfacl.c",
    ]
    if manifest["changed_sources"] != expected_changed:
        raise RuntimeError("acl normalization source set changed")

    regular = {
        "total": 15, "pass": 13, "skip": 0, "xfail": 2,
        "fail": 0, "xpass": 0, "error": 0,
    }
    platform = {
        "total": 1, "pass": 0, "skip": 0, "xfail": 0,
        "fail": 1, "xpass": 0, "error": 0,
    }
    compilers = {}
    source_sets = []
    prefix = "/rustbox-acl/normalized-source/"
    for compiler in ("gcc", "clang", "sanitizer"):
        database = base / f"{compiler}-compile-commands.json"
        commands = json.loads(database.read_text())
        sources = sorted({record["file"].removeprefix(prefix) for record in commands})
        if (
            len(commands) != 137 or len(sources) != 72
            or any(not record["file"].startswith(prefix) for record in commands)
        ):
            raise RuntimeError(f"normalized acl {compiler} compilation closure changed")
        source_sets.append(sources)
        test_log = base / f"{compiler}-check.log"
        if "runtime error:" in test_log.read_text(errors="replace"):
            raise RuntimeError(f"normalized acl {compiler} retains a sanitizer diagnostic")
        compilers[compiler] = {
            "compile_actions": len(commands),
            "compile_database_sha256": sha256(database),
            "upstream_tests": test_summary(test_log, regular),
            "platform_test": test_summary(
                base / f"{compiler}-platform-permissions.log", platform
            ),
            "test_log_sha256": sha256(test_log),
        }
    if any(sources != source_sets[0] for sources in source_sets[1:]):
        raise RuntimeError("normalized acl compiler source closures differ")
    if source_sets[0] != oracle["scope"]["production_sources"]:
        raise RuntimeError("normalized acl closure differs from canonical oracle")

    differentials = {}
    for compiler in ("gcc", "clang"):
        path = base / f"canonical-normalized-{compiler}-differential.json"
        report = json.loads(path.read_text())
        if report.get("cases") != 30 or report.get("passed") != 30:
            raise RuntimeError(f"normalized acl {compiler} differential changed")
        differentials[compiler] = {
            "comparisons": 30, "exact": True, "sha256": sha256(path),
        }

    entrypoints = {
        "chacl": "rustbox_chacl_main",
        "getfacl": "rustbox_getfacl_main",
        "setfacl": "rustbox_setfacl_main",
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
                raise RuntimeError(f"normalized acl dependency set changed: {libraries}")
            object_path = base / f"{applet}-{compiler}.o"
            defined = symbols(object_path)
            if not {"main", entrypoint}.issubset(defined):
                raise RuntimeError(f"normalized acl {applet} entrypoints changed")
            binaries[compiler][applet] = {
                "bytes": binary.stat().st_size,
                "sha256": sha256(binary),
                "needed": libraries,
                "embedded_libacl": True,
            }
            objects[compiler][applet] = {
                "sha256": sha256(object_path),
                "entrypoints": ["main", entrypoint],
            }

    resources = {}
    for applet in ("setfacl", "getfacl"):
        normalized_summary = heap_summary(base / f"valgrind-{applet}.log")
        canonical_summary = heap_summary(oracle_dir / f"valgrind-{applet}.log")
        if normalized_summary != canonical_summary:
            raise RuntimeError(f"normalized acl {applet} resource summary differs from canonical")
        resources[applet] = {
            "matches_canonical_summary": True,
            "heap_summary": normalized_summary,
            "log_sha256": sha256(base / f"valgrind-{applet}.log"),
        }

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-21",
        "release": "2.4.0",
        "normalization": manifest,
        "scope": {
            "production_sources": 72,
            "source_closure_matches_canonical": True,
            "compilers": compilers,
        },
        "canonical_normalized_differential": {
            "comparisons": 60, "exact": True, "compilers": differentials,
        },
        "resources": resources,
        "binaries": binaries,
        "entrypoint_objects": objects,
        "manifest_sha256": sha256(manifest_path),
        "configuration": {
            "nls": False, "selinux": False, "systemd": False,
            "leak_sanitizer_in_ptrace_fixture": False,
            "valgrind_leak_gate": True,
        },
        "next_gate": "translate the exact 72-source normalized acl production closure with C2Rust",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "changed_sources": 7, "differential": 60, "production_sources": 72,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
