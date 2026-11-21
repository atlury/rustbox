#!/usr/bin/env python3
"""Publish reproducible canonical-oracle evidence for attr 2.6.0."""

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
        raise RuntimeError(f"attr upstream test summary changed: {result}")
    return result


def needed(path: Path) -> list[str]:
    output = subprocess.run(
        ["readelf", "-d", str(path)], check=True, text=True, stdout=subprocess.PIPE
    ).stdout
    return re.findall(r"Shared library: \[([^]]+)\]", output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    oracle = repository / "work/analysis/attr-2.6.0/oracle"
    source = repository / "work/upstream/attr-2.6.0"
    state_path = repository / "work/upstream/.state/attr.json"
    state = json.loads(state_path.read_text())
    if not state["signature_verified"]:
        raise RuntimeError("attr release signature is not verified")

    compilers = {}
    source_sets = []
    prefix = "/rustbox-attr/source/"
    for compiler in ("gcc", "clang", "sanitizer"):
        database = oracle / f"{compiler}-compile-commands.json"
        commands = json.loads(database.read_text())
        sources = sorted({record["file"].removeprefix(prefix) for record in commands})
        if len(commands) != 21 or any(not record["file"].startswith(prefix) for record in commands):
            raise RuntimeError(f"attr {compiler} compilation closure changed")
        source_sets.append(sources)
        compilers[compiler] = {
            "compile_commands": len(commands),
            "compile_database_sha256": sha256(database),
            "upstream_tests": test_summary(oracle / f"{compiler}-check.log"),
            "test_log_sha256": sha256(oracle / f"{compiler}-check.log"),
        }
    if any(sources != source_sets[0] for sources in source_sets[1:]):
        raise RuntimeError("attr compiler source closures differ")
    production_sources = source_sets[0]
    source_lines = {
        name: (source / name).read_text(errors="replace").count("\n")
        for name in production_sources
    }

    differential_path = oracle / "differential.json"
    differential = json.loads(differential_path.read_text())
    if differential["cases"] != 22 or differential["passed"] != 22:
        raise RuntimeError("attr canonical differential suite is incomplete")

    valgrind = {}
    expected_heaps = {
        "setfattr": [
            "in use at exit: 256 bytes in 1 blocks",
            "total heap usage: 1 allocs, 0 frees, 256 bytes allocated",
            "still reachable: 256 bytes in 1 blocks",
        ],
        "getfattr": [
            "in use at exit: 2,152 bytes in 42 blocks",
            "total heap usage: 48 allocs, 6 frees, 7,264 bytes allocated",
            "still reachable: 2,152 bytes in 42 blocks",
        ],
    }
    for utility, phrases in expected_heaps.items():
        path = oracle / f"valgrind-{utility}.log"
        text = path.read_text(errors="replace")
        required = [
            *phrases,
            "definitely lost: 0 bytes in 0 blocks",
            "indirectly lost: 0 bytes in 0 blocks",
            "possibly lost: 0 bytes in 0 blocks",
            "ERROR SUMMARY: 0 errors",
        ]
        if any(phrase not in text for phrase in required):
            raise RuntimeError(f"attr {utility} Valgrind baseline changed")
        valgrind[utility] = {"errors": 0, "heap_summary": phrases, "log_sha256": sha256(path)}

    binaries = {}
    for utility in ("attr", "getfattr", "setfattr"):
        variants = {}
        for compiler in ("gcc", "clang"):
            path = oracle / f"{utility}-{compiler}"
            dependencies = needed(path)
            if dependencies != ["libc.so.6"]:
                raise RuntimeError(f"unexpected attr dependency set: {dependencies}")
            variants[compiler] = {
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "needed": dependencies,
            }
        binaries[utility] = variants

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-21",
        "release": "2.6.0",
        "status": "complete canonical oracle; production static analysis pending",
        "source": {
            "archive_sha256": state["sha256"],
            "signature_sha256": state["signature_sha256"],
            "signer_fingerprint": state["signer_fingerprint"],
            "archive_members_verified": 147,
            "state_sha256": sha256(state_path),
        },
        "scope": {
            "public_names": ["attr", "getfattr", "setfattr"],
            "production_sources": production_sources,
            "production_source_count": len(production_sources),
            "production_lines": sum(source_lines.values()),
            "source_lines": source_lines,
        },
        "compilers": compilers,
        "cross_compiler_differential": {
            **differential,
            "report_sha256": sha256(differential_path),
        },
        "resource_checks": valgrind,
        "binaries": binaries,
        "configuration": {"nls": False, "shared_library": False, "selinux": False, "systemd": False},
        "test_policy": {
            "run_as": "nobody",
            "intentional_skip": "root-only trusted.* symlink xattr case; Docker root lacks the required kernel capability",
            "ordinary_upstream_components_passed": 2,
        },
        "next_gate": "audit the exact 21-unit production closure with independent analyzers",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"differential": 22, "production_sources": 21, "utilities": 3}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
