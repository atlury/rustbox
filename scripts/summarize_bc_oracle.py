#!/usr/bin/env python3
"""Generate committed evidence for the canonical GNU bc 1.08.2 oracle."""

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


def source_closure(database: Path) -> tuple[list[str], int]:
    records = json.loads(database.read_text())
    prefix = "/rustbox-bc/source/"
    sources: set[str] = set()
    for record in records:
        source = str(record["file"])
        if not source.startswith(prefix):
            raise RuntimeError(f"unexpected GNU bc compile source {source}")
        relative = source.removeprefix(prefix)
        if not relative.startswith(("bc/", "dc/", "lib/")):
            raise RuntimeError(f"unexpected GNU bc production source {relative}")
        sources.add(relative)
    return sorted(sources), len(records)


def passed_tests(path: Path) -> list[str]:
    records = []
    for line in path.read_text().splitlines():
        match = re.fullmatch(r"(\S+) pass", line)
        if not match:
            raise RuntimeError(f"unexpected GNU bc test record in {path}: {line!r}")
        records.append(match.group(1))
    return records


def valgrind_summary(path: Path) -> dict[str, object]:
    text = path.read_text(errors="replace")
    if "ERROR SUMMARY: 0 errors" not in text:
        raise RuntimeError(f"GNU bc Valgrind errors in {path}")
    heap = re.search(
        r"in use at exit: ([0-9,]+) bytes in ([0-9,]+) blocks.*?"
        r"total heap usage: ([0-9,]+) allocs, ([0-9,]+) frees, ([0-9,]+) bytes allocated",
        text,
        re.DOTALL,
    )
    if not heap:
        raise RuntimeError(f"GNU bc Valgrind heap summary missing in {path}")
    values = [int(value.replace(",", "")) for value in heap.groups()]
    return {
        "bytes_at_exit": values[0],
        "blocks_at_exit": values[1],
        "allocations": values[2],
        "frees": values[3],
        "bytes_allocated": values[4],
        "errors": 0,
        "log_sha256": sha256(path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    oracle = repository / "work/analysis/bc-1.08.2/oracle"
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["bc"]
    state = json.loads((repository / "work/upstream/.state/bc.json").read_text())
    for key in ("version", "sha256", "signature_sha256", "signer_fingerprint", "key_sha256"):
        if state.get(key) != release[key]:
            raise RuntimeError(f"GNU bc source state changed at {key}")
    if not state["signature_verified"]:
        raise RuntimeError("GNU bc release signature is not verified")

    source_sets: dict[str, list[str]] = {}
    compile_actions: dict[str, int] = {}
    compile_hashes: dict[str, str] = {}
    for compiler in ("gcc", "clang", "sanitizer"):
        database = oracle / f"{compiler}-compile-commands.json"
        source_sets[compiler], compile_actions[compiler] = source_closure(database)
        compile_hashes[compiler] = sha256(database)
    if any(sources != source_sets["gcc"] for sources in source_sets.values()):
        raise RuntimeError("GNU bc compiler production closures differ")
    if len(source_sets["gcc"]) != 21:
        raise RuntimeError(f"GNU bc production closure changed: {len(source_sets['gcc'])}")

    canonical_tests = sorted(path.name for path in (repository / "work/upstream/bc-1.08.2/Test").iterdir()
                             if path.suffix in (".b", ".bc"))
    actual_tests = {
        compiler: passed_tests(oracle / f"{compiler}-upstream-tests.log")
        for compiler in ("gcc", "clang", "sanitizer")
    }
    if sorted(actual_tests["gcc"]) != canonical_tests or sorted(actual_tests["clang"]) != canonical_tests:
        raise RuntimeError("GNU bc canonical shipped-test coverage changed")
    sanitizer_expected = [name for name in canonical_tests if name != "checklib.b"]
    if sorted(actual_tests["sanitizer"]) != sanitizer_expected:
        raise RuntimeError("GNU bc sanitizer shipped-test coverage changed")

    differential = json.loads((oracle / "differential.json").read_text())
    if differential.get("cases") != 46 or differential.get("passed") != 46:
        raise RuntimeError("GNU bc cross-compiler differential is incomplete")

    source_root = repository / "work/upstream/bc-1.08.2"
    production_lines = sum(
        len((source_root / name).read_text(errors="replace").splitlines())
        for name in source_sets["gcc"]
    )
    binaries: dict[str, dict[str, object]] = {}
    for compiler in ("gcc", "clang"):
        binaries[compiler] = {}
        for applet in ("bc", "dc"):
            binary = oracle / f"{applet}-{compiler}"
            libraries = needed(binary)
            if libraries != ["libc.so.6"]:
                raise RuntimeError(f"unexpected GNU {applet} {compiler} dependencies: {libraries}")
            binaries[compiler][applet] = {
                "bytes": binary.stat().st_size,
                "sha256": sha256(binary),
                "needed": libraries,
            }

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-21",
        "release": {
            "version": release["version"],
            "bundled_dc_version": "1.5.2",
            "archive": release["archive"],
            "sha256": release["sha256"],
            "signature_sha256": release["signature_sha256"],
            "signature_verified": True,
            "signer_fingerprint": release["signer_fingerprint"],
            "signing_key_sha256": release["key_sha256"],
        },
        "scope": {
            "executables": ["bc", "dc"],
            "production_sources": source_sets["gcc"],
            "production_source_count": len(source_sets["gcc"]),
            "production_lines": production_lines,
            "captured_compile_actions": compile_actions,
            "compile_database_sha256": compile_hashes,
        },
        "configuration": {
            "readline": False,
            "libedit": False,
            "oracle_dynamic_dependencies": ["libc.so.6"],
            "generated_release_parser_and_scanner_used": True,
            "sanitizer_policy": {
                "asan": "detect_leaks=1:halt_on_error=1",
                "ubsan": "halt_on_error=1",
                "excluded_throughput_case": "checklib.b",
                "reason": "full high-precision transcendental workload runs under both canonical compilers; sanitizer covers every smaller shipped workload",
            },
        },
        "tests": {
            compiler: {
                "automake_check_log_sha256": sha256(oracle / f"{compiler}-check.log"),
                "shipped_cases": len(names),
                "shipped_case_names": names,
                "shipped_log_sha256": sha256(oracle / f"{compiler}-upstream-tests.log"),
            }
            for compiler, names in actual_tests.items()
        },
        "cross_compiler_differential": {
            "comparisons": 46,
            "exact": True,
            "report_sha256": sha256(oracle / "differential.json"),
        },
        "valgrind": {
            "bc": valgrind_summary(oracle / "valgrind-bc.log"),
            "dc": valgrind_summary(oracle / "valgrind-dc.log"),
        },
        "binaries": binaries,
        "next_gate": "production-only static analysis followed by deterministic multicall-entrypoint normalization",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"differential": 46, "production_sources": 21, "utilities": 2}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
