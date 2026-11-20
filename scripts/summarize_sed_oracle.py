#!/usr/bin/env python3
"""Generate committed evidence for the canonical GNU sed 4.10 oracle."""

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


def summaries(path: Path) -> list[dict[str, int]]:
    text = path.read_text(errors="replace")
    matches = re.findall(
        r"# TOTAL:\s+(\d+).*?# PASS:\s+(\d+).*?# SKIP:\s+(\d+).*?"
        r"# XFAIL:\s+(\d+).*?# FAIL:\s+(\d+).*?# XPASS:\s+(\d+).*?# ERROR:\s+(\d+)",
        text,
        re.DOTALL,
    )
    names = ("total", "pass", "skip", "xfail", "fail", "xpass", "error")
    return [dict(zip(names, map(int, values))) for values in matches]


def source_name(path: str, compiler: str) -> str:
    source_prefix = "/rustbox-sed/source/"
    if path.startswith(source_prefix):
        return path.removeprefix(source_prefix)
    generated = f"/rustbox-sed/oracle-{compiler}/sed/version.c"
    if path == generated:
        return "sed/version.c"
    raise RuntimeError(f"unexpected GNU sed source path: {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    oracle = repository / "work/analysis/sed-4.10/oracle"
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["sed"]
    state = json.loads((repository / "work/upstream/.state/sed.json").read_text())
    for key in ("version", "sha256", "signature_sha256", "signer_fingerprint", "key_sha256"):
        if state.get(key) != release[key]:
            raise RuntimeError(f"GNU sed source state changed at {key}")
    if not state["signature_verified"]:
        raise RuntimeError("GNU sed release signature is not verified")

    expected_release = [
        {"total": 75, "pass": 68, "skip": 7, "xfail": 0, "fail": 0, "xpass": 0, "error": 0},
        {"total": 287, "pass": 241, "skip": 46, "xfail": 0, "fail": 0, "xpass": 0, "error": 0},
    ]
    tests: dict[str, object] = {}
    for compiler in ("gcc", "clang"):
        actual = summaries(oracle / f"{compiler}-check.log")
        if actual != expected_release:
            raise RuntimeError(f"GNU sed {compiler} suites changed: {actual}")
        tests[compiler] = {"sed": actual[0], "gnulib": actual[1]}
    sanitizer = summaries(oracle / "sanitizer-check.log")
    expected_sanitizer = [
        {"total": 75, "pass": 64, "skip": 11, "xfail": 0, "fail": 0, "xpass": 0, "error": 0}
    ]
    if sanitizer != expected_sanitizer:
        raise RuntimeError(f"GNU sed sanitizer suite changed: {sanitizer}")
    tests["sanitizer"] = {"sed": sanitizer[0], "leak_detection": "Valgrind"}

    source_sets: dict[str, list[str]] = {}
    compile_actions: dict[str, int] = {}
    production_actions: dict[str, int] = {}
    compile_hashes: dict[str, str] = {}
    for compiler in ("gcc", "clang", "sanitizer"):
        database = oracle / f"{compiler}-compile-commands.json"
        records = json.loads(database.read_text())
        names = sorted({source_name(record["file"], compiler) for record in records})
        production = [name for name in names if not name.startswith("gnulib-tests/")]
        if len(records) != 121 or len(names) != 121 or len(production) != 85:
            raise RuntimeError(f"GNU sed {compiler} source closure changed")
        source_sets[compiler] = production
        compile_actions[compiler] = len(records)
        production_actions[compiler] = len(production)
        compile_hashes[compiler] = sha256(database)
    if not (source_sets["gcc"] == source_sets["clang"] == source_sets["sanitizer"]):
        raise RuntimeError("GNU sed compiler production closures differ")

    source_root = repository / "work/upstream/sed-4.10"
    production_lines = 0
    for name in source_sets["gcc"]:
        path = oracle / "version.c" if name == "sed/version.c" else source_root / name
        production_lines += len(path.read_text(errors="replace").splitlines())

    expected_needed = {"libacl.so.1", "libattr.so.1", "libc.so.6"}
    binaries = {}
    for compiler in ("gcc", "clang"):
        binary = oracle / f"sed-{compiler}"
        libraries = needed(binary)
        if set(libraries) != expected_needed:
            raise RuntimeError(f"unexpected GNU sed {compiler} dependencies: {libraries}")
        binaries[compiler] = {
            "bytes": binary.stat().st_size,
            "sha256": sha256(binary),
            "needed": libraries,
            "config_sha256": sha256(oracle / f"config-{compiler}.h"),
        }

    differential = json.loads((oracle / "differential.json").read_text())
    if differential["comparisons"] != 30 or not differential["gcc_clang_exact"]:
        raise RuntimeError("GNU sed differential is incomplete")
    valgrind = (oracle / "valgrind.log").read_text(errors="replace")
    for phrase in (
        "ERROR SUMMARY: 0 errors",
        "definitely lost: 0 bytes in 0 blocks",
        "indirectly lost: 0 bytes in 0 blocks",
        "possibly lost: 0 bytes in 0 blocks",
    ):
        if phrase not in valgrind:
            raise RuntimeError("GNU sed Valgrind smoke is incomplete")

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
            "executables": ["sed"],
            "all_compile_actions": compile_actions,
            "production_compile_actions": production_actions,
            "unique_production_sources": 85,
            "program_sources": [name for name in source_sets["gcc"] if name.startswith("sed/")],
            "gnulib_sources": [name for name in source_sets["gcc"] if name.startswith("lib/")],
            "production_lines": production_lines,
            "production_sources": source_sets["gcc"],
            "compile_database_sha256": compile_hashes,
        },
        "configuration": {
            "selinux": False,
            "acl": True,
            "extended_attributes": True,
            "oracle_dynamic_dependencies": sorted(expected_needed),
            "final_rustbox_policy": "no external runtime libraries; absorb or replace ACL/xattr support before release",
        },
        "tests": {
            compiler: {**summary, "log_sha256": sha256(oracle / f"{compiler}-check.log")}
            for compiler, summary in tests.items()
        },
        "cross_compiler_differential": {
            "comparisons": 30,
            "exact": True,
            "report_sha256": sha256(oracle / "differential.json"),
        },
        "valgrind": {
            "errors": 0,
            "definite_indirect_possible_leaks": 0,
            "still_reachable_bytes": 4317,
            "log_sha256": sha256(oracle / "valgrind.log"),
        },
        "binaries": binaries,
        "next_gate": "production-only static analysis followed by deterministic multicall entrypoint normalization",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"differential": 30, "production_sources": 85, "release_tests": 362}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

