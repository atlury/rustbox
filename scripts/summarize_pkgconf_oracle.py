#!/usr/bin/env python3
"""Generate committed evidence for the canonical pkgconf 3.0.11 oracle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


TOOLS = ("pkgconf", "bomtool", "pccritic", "spdxtool")
TARGET_PREFIXES = ("libpkgconf.a.p/", "pkgconf.p/", "bomtool.p/", "pccritic.p/", "spdxtool.p/")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_records(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def symbols(path: Path) -> list[str]:
    result = []
    for line in path.read_text(errors="replace").splitlines():
        fields = line.split()
        if len(fields) >= 3 and len(fields[-2]) == 1 and fields[-2].isupper():
            result.append(fields[-1])
    return sorted(set(result))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    oracle = repository / "work/analysis/pkgconf-3.0.11/oracle"
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["pkgconf"]
    state = json.loads((repository / "work/upstream/.state/pkgconf.json").read_text())
    for key in ("version", "tag", "commit", "tree", "signer_fingerprint", "key_sha256"):
        if state.get(key) != release[key]:
            raise RuntimeError(f"pkgconf source state changed at {key}")
    if not state["signature_verified"]:
        raise RuntimeError("pkgconf signed tag is not verified")

    tests: dict[str, list[dict[str, object]]] = {
        name: test_records(oracle / f"{name}-testlog.json")
        for name in ("gcc", "clang", "sanitizer")
    }
    expected_counts = {"gcc": 32, "clang": 32, "sanitizer": 33}
    for name, records in tests.items():
        if len(records) != expected_counts[name] or any(record["result"] != "OK" for record in records):
            raise RuntimeError(f"pkgconf {name} test suite is incomplete")
    if "api-oom-spdxtool" not in {record["name"] for record in tests["sanitizer"]}:
        raise RuntimeError("pkgconf shared-only allocation-failure test is absent")

    compile_actions: dict[str, int] = {}
    production_sources: dict[str, list[str]] = {}
    compile_database_hashes: dict[str, str] = {}
    for compiler in ("gcc", "clang"):
        path = oracle / f"{compiler}-compile-commands.json"
        records = json.loads(path.read_text())
        production = [
            record for record in records
            if str(record.get("output", "")).startswith(TARGET_PREFIXES)
        ]
        sources = sorted({str(record["file"]).removeprefix("../source/") for record in production})
        if len(production) != 38 or len(sources) != 35:
            raise RuntimeError(f"pkgconf {compiler} production closure changed")
        compile_actions[compiler] = len(production)
        production_sources[compiler] = sources
        compile_database_hashes[compiler] = sha256(path)
    if production_sources["gcc"] != production_sources["clang"]:
        raise RuntimeError("pkgconf GCC and Clang source closures differ")

    exported = {compiler: symbols(oracle / f"libpkgconf-{compiler}.symbols") for compiler in ("gcc", "clang")}
    if exported["gcc"] != exported["clang"] or len(exported["gcc"]) != 176:
        raise RuntimeError("pkgconf static-library public symbols differ")

    binaries: dict[str, dict[str, object]] = {}
    public_surface: dict[str, dict[str, str]] = {}
    for compiler in ("gcc", "clang"):
        for tool in TOOLS:
            binary = oracle / f"{tool}-{compiler}"
            dynamic = (oracle / f"{tool}-{compiler}.dynamic").read_text()
            needed = re.findall(r"Shared library: \[([^]]+)\]", dynamic)
            if needed != ["libc.so.6"]:
                raise RuntimeError(f"unexpected {tool}-{compiler} dependencies: {needed}")
            binaries[f"{tool}-{compiler}"] = {
                "bytes": binary.stat().st_size,
                "sha256": sha256(binary),
                "needed": needed,
            }
            public_surface[f"{tool}-{compiler}"] = {
                kind: sha256(oracle / f"{tool}-{compiler}.{kind}.out")
                for kind in ("help", "version")
            }
    for tool in TOOLS:
        for kind in ("help", "version"):
            if public_surface[f"{tool}-gcc"][kind] != public_surface[f"{tool}-clang"][kind]:
                raise RuntimeError(f"pkgconf {tool} {kind} differs by compiler")

    valgrind_summary = (oracle / "valgrind-test.log").read_text(errors="replace")
    for pattern in (r"^Ok:\s+32", r"^Fail:\s+0", r"^Skipped:\s+0"):
        if not re.search(pattern, valgrind_summary, re.MULTILINE):
            raise RuntimeError("pkgconf Valgrind suite is incomplete")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-20",
        "release": {
            "version": release["version"],
            "repository": release["repository"],
            "tag": release["tag"],
            "commit": release["commit"],
            "tree": release["tree"],
            "signature_verified": True,
            "signer_fingerprint": release["signer_fingerprint"],
            "signing_key_sha256": release["key_sha256"],
        },
        "scope": {
            "executables": list(TOOLS),
            "compatible_aliases": {"pkg-config": "pkgconf"},
            "production_compile_actions": compile_actions,
            "unique_production_sources": len(production_sources["gcc"]),
            "production_sources": production_sources["gcc"],
            "compile_database_sha256": compile_database_hashes,
        },
        "tests": {
            name: {
                "total": len(records),
                "passed": len(records),
                "skipped": 0,
                "names": [record["name"] for record in records],
                "log_sha256": sha256(oracle / f"{name}-testlog.json"),
            }
            for name, records in tests.items()
        },
        "valgrind": {
            "tests": 32,
            "passed": 32,
            "errors_for_leak_kinds": ["definite", "indirect", "possible"],
            "summary_sha256": sha256(oracle / "valgrind-test.log"),
            "full_log_sha256": sha256(oracle / "valgrind-testlog.txt"),
        },
        "abi": {
            "static_library_symbols": len(exported["gcc"]),
            "gcc_clang_exact": True,
            "symbols": exported["gcc"],
        },
        "public_surface": public_surface,
        "binaries": binaries,
        "next_gate": "production-only static analysis followed by deterministic multicall entrypoint normalization",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "executables": len(TOOLS),
        "production_sources": len(production_sources["gcc"]),
        "sanitizer_tests": len(tests["sanitizer"]),
        "static_symbols": len(exported["gcc"]),
        "tests_per_compiler": len(tests["gcc"]),
        "valgrind_tests": 32,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
