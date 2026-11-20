#!/usr/bin/env python3
"""Generate committed evidence for the canonical GNU patch 2.8 oracle."""

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


def test_summary(path: Path) -> dict[str, int]:
    text = path.read_text(errors="replace")
    values = {}
    for name in ("TOTAL", "PASS", "SKIP", "XFAIL", "FAIL", "XPASS", "ERROR"):
        match = re.search(rf"^# {name}:\s+(\d+)$", text, re.MULTILINE)
        if not match:
            raise RuntimeError(f"missing {name} summary in {path}")
        values[name.lower()] = int(match.group(1))
    expected = {"total": 49, "pass": 47, "skip": 0, "xfail": 2, "fail": 0, "xpass": 0, "error": 0}
    if values != expected or "PASS: ed-style" not in text:
        raise RuntimeError(f"GNU patch suite is incomplete in {path}: {values}")
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    oracle = repository / "work/analysis/patch-2.8/oracle"
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["patch"]
    state = json.loads((repository / "work/upstream/.state/patch.json").read_text())
    for key in ("version", "sha256", "signature_sha256", "signer_fingerprint", "key_sha256"):
        if state.get(key) != release[key]:
            raise RuntimeError(f"GNU patch source state changed at {key}")
    if not state["signature_verified"]:
        raise RuntimeError("GNU patch release signature is not verified")

    tests = {
        compiler: test_summary(oracle / f"{compiler}-check.log")
        for compiler in ("gcc", "clang", "sanitizer")
    }
    source_sets: dict[str, list[str]] = {}
    compile_actions: dict[str, int] = {}
    compile_hashes: dict[str, str] = {}
    for compiler in ("gcc", "clang", "sanitizer"):
        database = oracle / f"{compiler}-compile-commands.json"
        records = json.loads(database.read_text())
        sources = sorted({str(record["file"]).removeprefix("/rustbox-patch/source/") for record in records})
        if len(records) != 67 or len(sources) != 67:
            raise RuntimeError(f"GNU patch {compiler} production closure changed")
        source_sets[compiler] = sources
        compile_actions[compiler] = len(records)
        compile_hashes[compiler] = sha256(database)
    if not (source_sets["gcc"] == source_sets["clang"] == source_sets["sanitizer"]):
        raise RuntimeError("GNU patch compiler source closures differ")

    source_root = repository / "work/upstream/patch-2.8"
    production_lines = sum(
        len((source_root / name).read_text(errors="replace").splitlines())
        for name in source_sets["gcc"]
    )
    expected_needed = {"libattr.so.1", "libc.so.6"}
    binaries = {}
    for compiler in ("gcc", "clang"):
        binary = oracle / f"patch-{compiler}"
        libraries = needed(binary)
        if set(libraries) != expected_needed:
            raise RuntimeError(f"unexpected GNU patch {compiler} dependencies: {libraries}")
        binaries[compiler] = {
            "bytes": binary.stat().st_size,
            "sha256": sha256(binary),
            "needed": libraries,
            "config_sha256": sha256(oracle / f"config-{compiler}.h"),
        }

    differential = json.loads((oracle / "differential.json").read_text())
    if differential["comparisons"] != 28 or not differential["gcc_clang_exact"]:
        raise RuntimeError("GNU patch cross-compiler differential is incomplete")
    valgrind = (oracle / "valgrind.log").read_text(errors="replace")
    for phrase in (
        "ERROR SUMMARY: 0 errors",
        "definitely lost: 0 bytes in 0 blocks",
        "indirectly lost: 0 bytes in 0 blocks",
        "possibly lost: 0 bytes in 0 blocks",
    ):
        if phrase not in valgrind:
            raise RuntimeError("GNU patch Valgrind smoke is incomplete")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-20",
        "release": {
            "version": release["version"],
            "archive": release["archive"],
            "sha256": release["sha256"],
            "signature_sha256": release["signature_sha256"],
            "signature_verified": True,
            "signer_fingerprint": release["signer_fingerprint"],
            "signing_key_sha256": release["key_sha256"],
        },
        "scope": {
            "executables": ["patch"],
            "production_compile_actions": compile_actions,
            "unique_production_sources": 67,
            "program_sources": [name for name in source_sets["gcc"] if name.startswith("src/")],
            "gnulib_sources": [name for name in source_sets["gcc"] if name.startswith("lib/")],
            "production_lines": production_lines,
            "production_sources": source_sets["gcc"],
            "compile_database_sha256": compile_hashes,
        },
        "configuration": {
            "extended_attributes": True,
            "ed_style_tested": True,
            "oracle_dynamic_dependencies": sorted(expected_needed),
            "final_rustbox_policy": "no external runtime libraries; replace or statically integrate libattr before release",
        },
        "tests": {
            compiler: {**summary, "log_sha256": sha256(oracle / f"{compiler}-check.log")}
            for compiler, summary in tests.items()
        },
        "cross_compiler_differential": {
            "comparisons": 28,
            "exact": True,
            "report_sha256": sha256(oracle / "differential.json"),
        },
        "valgrind": {
            "errors": 0,
            "definite_indirect_possible_leaks": 0,
            "still_reachable_bytes": 2947,
            "log_sha256": sha256(oracle / "valgrind.log"),
        },
        "binaries": binaries,
        "next_gate": "production-only static analysis followed by deterministic multicall entrypoint normalization",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"differential": 28, "production_sources": 67, "tests_per_build": 49}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
