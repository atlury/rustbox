#!/usr/bin/env python3
"""Publish reproducible canonical-oracle evidence for acl 2.4.0."""

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
        raise RuntimeError(f"acl test summary changed in {path}: {result}")
    return result


def needed(path: Path) -> list[str]:
    process = subprocess.run(
        ["readelf", "-d", str(path)], check=True, text=True, stdout=subprocess.PIPE
    )
    return re.findall(r"Shared library: \[([^]]+)\]", process.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    oracle = repository / "work/analysis/acl-2.4.0/oracle"
    source = repository / "work/upstream/acl-2.4.0"
    state_path = repository / "work/upstream/.state/acl.json"
    state = json.loads(state_path.read_text())
    if not state["signature_verified"]:
        raise RuntimeError("acl release signature is not verified")

    regular_expected = {
        "total": 15, "pass": 13, "skip": 0, "xfail": 2,
        "fail": 0, "xpass": 0, "error": 0,
    }
    platform_expected = {
        "total": 1, "pass": 0, "skip": 0, "xfail": 0,
        "fail": 1, "xpass": 0, "error": 0,
    }
    compilers = {}
    source_sets = []
    prefix = "/rustbox-acl/source/"
    for compiler in ("gcc", "clang", "sanitizer"):
        database = oracle / f"{compiler}-compile-commands.json"
        commands = json.loads(database.read_text())
        sources = sorted({record["file"].removeprefix(prefix) for record in commands})
        if (
            len(commands) != 137 or len(sources) != 72
            or any(not record["file"].startswith(prefix) for record in commands)
        ):
            raise RuntimeError(f"acl {compiler} compilation closure changed")
        source_sets.append(sources)
        expected = regular_expected if compiler != "sanitizer" else {
            "total": 15, "pass": 12, "skip": 0, "xfail": 2,
            "fail": 1, "xpass": 0, "error": 0,
        }
        compilers[compiler] = {
            "compile_actions": len(commands),
            "compile_database_sha256": sha256(database),
            "upstream_tests": test_summary(oracle / f"{compiler}-check.log", expected),
            "platform_test": test_summary(
                oracle / f"{compiler}-platform-permissions.log", platform_expected
            ),
            "test_log_sha256": sha256(oracle / f"{compiler}-check.log"),
            "platform_log_sha256": sha256(
                oracle / f"{compiler}-platform-permissions.log"
            ),
        }
    if any(sources != source_sets[0] for sources in source_sets[1:]):
        raise RuntimeError("acl compiler source closures differ")
    production_sources = source_sets[0]
    source_lines = {
        name: (source / name).read_text(errors="replace").count("\n")
        for name in production_sources
    }

    differential_path = oracle / "differential.json"
    differential = json.loads(differential_path.read_text())
    if differential["cases"] != 30 or differential["passed"] != 30:
        raise RuntimeError("acl canonical differential suite is incomplete")

    valgrind = {}
    for utility in ("setfacl", "getfacl"):
        path = oracle / f"valgrind-{utility}.log"
        text = path.read_text(errors="replace")
        required = [
            "All heap blocks were freed -- no leaks are possible",
            "ERROR SUMMARY: 0 errors",
        ]
        if any(phrase not in text for phrase in required):
            raise RuntimeError(f"acl {utility} Valgrind baseline changed")
        heap = re.search(r"total heap usage: ([^\n]+)", text)
        valgrind[utility] = {
            "errors": 0,
            "heap_summary": heap.group(1) if heap else "none",
            "log_sha256": sha256(path),
        }

    binaries = {}
    for utility in ("chacl", "getfacl", "setfacl"):
        variants = {}
        for compiler in ("gcc", "clang"):
            path = oracle / f"{utility}-{compiler}"
            dependencies = needed(path)
            if dependencies != ["libc.so.6"]:
                raise RuntimeError(f"unexpected acl dependency set: {dependencies}")
            variants[compiler] = {
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "needed": dependencies,
                "embedded_libacl": True,
            }
        binaries[utility] = variants

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-21",
        "release": "2.4.0",
        "status": "complete canonical oracle; production static analysis pending",
        "source": {
            "archive_sha256": state["sha256"],
            "signature_sha256": state["signature_sha256"],
            "signer_fingerprint": state["signer_fingerprint"],
            "archive_members_verified": 274,
            "state_sha256": sha256(state_path),
        },
        "scope": {
            "public_names": ["chacl", "getfacl", "setfacl"],
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
        "configuration": {
            "nls": False,
            "shared_library_during_tests": True,
            "standalone_oracles_embed_libacl": True,
            "selinux": False,
            "systemd": False,
        },
        "test_policy": {
            "ordinary_tests_passed": 13,
            "canonical_nfs_xfails": 2,
            "container_platform_failure": (
                "root permission/device case requires host kernel semantics absent "
                "from the Docker environment; its exact one-test failure is pinned"
            ),
            "asan_preload_policy": (
                "verify_asan_link_order is disabled only because the canonical identity "
                "fixture deliberately preloads libtestlookup"
            ),
            "canonical_undefined_behavior": (
                "four null-pointer offset diagnostics at __libobj.c:82 make the "
                "root setfacl test fail under UBSan; the exact log is pinned and "
                "the ordering fix is required in deterministic normalization"
            ),
        },
        "next_gate": "audit the exact 72-unit production closure with independent analyzers",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"differential": 30, "production_sources": 72, "utilities": 3}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
