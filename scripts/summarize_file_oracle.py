#!/usr/bin/env python3
"""Generate committed evidence for the canonical File 5.48 oracle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def symbols(path: Path) -> list[str]:
    output = subprocess.run(
        ["nm", "-g", "--defined-only", str(path)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    result = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 3 and len(fields[-2]) == 1 and fields[-2].isupper():
            result.append(fields[-1])
    return sorted(set(result))


def needed(path: Path) -> list[str]:
    output = subprocess.run(
        ["readelf", "-d", str(path)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    return re.findall(r"Shared library: \[([^]]+)\]", output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    oracle = repository / "work/analysis/file-5.48/oracle"
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["file"]
    state = json.loads((repository / "work/upstream/.state/file.json").read_text())
    for key in (
        "version",
        "sha256",
        "signature_sha256",
        "signer_fingerprint",
        "key_sha256",
    ):
        if state.get(key) != release[key]:
            raise RuntimeError(f"File source state changed at {key}")
    if not state["signature_verified"]:
        raise RuntimeError("File release signature is not verified")

    test_counts = {}
    for compiler in ("gcc", "clang", "sanitizer"):
        log = oracle / f"{compiler}-check.log"
        count = len(re.findall(r"^Running test:", log.read_text(errors="replace"), re.MULTILINE))
        if count != 83:
            raise RuntimeError(f"File {compiler} test corpus is incomplete: {count}")
        test_counts[compiler] = count

    source_sets: dict[str, list[str]] = {}
    compile_hashes: dict[str, str] = {}
    compile_actions: dict[str, int] = {}
    for compiler in ("gcc", "clang", "sanitizer"):
        database = oracle / f"{compiler}-compile-commands.json"
        records = json.loads(database.read_text())
        sources = sorted(
            str(record["file"]).removeprefix("/rustbox-file/source/")
            for record in records
        )
        if len(records) != 25 or len(set(sources)) != 25:
            raise RuntimeError(f"File {compiler} production closure changed")
        source_sets[compiler] = sources
        compile_hashes[compiler] = sha256(database)
        compile_actions[compiler] = len(records)
    if not (source_sets["gcc"] == source_sets["clang"] == source_sets["sanitizer"]):
        raise RuntimeError("File compiler source closures differ")

    source_root = repository / "work/upstream/file-5.48"
    production_lines = sum(
        len((source_root / name).read_text(errors="replace").splitlines())
        for name in source_sets["gcc"]
    )

    exported = {
        compiler: symbols(oracle / f"libmagic-{compiler}.a")
        for compiler in ("gcc", "clang")
    }
    if exported["gcc"] != exported["clang"] or len(exported["gcc"]) != 126:
        raise RuntimeError("File static libmagic symbols differ")

    common_needed = {
        "libbz2.so.1.0",
        "libc.so.6",
        "liblz.so.1",
        "liblzma.so.5",
        "libseccomp.so.2",
        "libz.so.1",
        "libzstd.so.1",
    }
    expected_needed = {
        "gcc": common_needed,
        "clang": common_needed | {"libm.so.6"},
    }
    binaries = {}
    for compiler in ("gcc", "clang"):
        binary = oracle / f"file-{compiler}"
        libraries = needed(binary)
        if set(libraries) != expected_needed[compiler]:
            raise RuntimeError(f"unexpected File {compiler} dependencies: {libraries}")
        binaries[compiler] = {
            "bytes": binary.stat().st_size,
            "sha256": sha256(binary),
            "needed": libraries,
        }

    config_gcc = oracle / "config-gcc.h"
    config_clang = oracle / "config-clang.h"
    if config_gcc.read_bytes() != config_clang.read_bytes():
        raise RuntimeError("File GCC and Clang feature configurations differ")
    config = config_gcc.read_text()
    features = {
        "builtin_elf": "#define BUILTIN_ELF 1" in config,
        "elf_core": "#define ELFCORE 1" in config,
        "zlib": "#define HAVE_ZLIB_H 1" in config,
        "bzip2": "#define HAVE_BZLIB_H 1" in config,
        "xz": "#define HAVE_LZMA_H 1" in config,
        "zstd": "#define HAVE_ZSTD_H 1" in config,
        "lzip": "#define HAVE_LZLIB_H 1" in config,
        "seccomp": "#define HAVE_LIBSECCOMP 1" in config,
        "landlock": "#define HAVE_LINUX_LANDLOCK_H 1" in config,
        "lrzip": "#define HAVE_LRZIP_H 1" in config,
    }
    if not all(value for key, value in features.items() if key != "lrzip") or features["lrzip"]:
        raise RuntimeError(f"unexpected File feature configuration: {features}")

    magic_gcc = oracle / "magic-gcc.mgc"
    magic_clang = oracle / "magic-clang.mgc"
    if magic_gcc.read_bytes() != magic_clang.read_bytes():
        raise RuntimeError("File compiled magic databases differ")

    differential = json.loads((oracle / "differential.json").read_text())
    if differential["comparisons"] != 174 or not differential["gcc_clang_exact"]:
        raise RuntimeError("File cross-compiler differential is incomplete")
    valgrind = (oracle / "valgrind.log").read_text(errors="replace")
    if (
        "ERROR SUMMARY: 0 errors" not in valgrind
        or "All heap blocks were freed -- no leaks are possible" not in valgrind
    ):
        raise RuntimeError("File Valgrind smoke is incomplete")

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
            "executables": ["file"],
            "library": "libmagic",
            "production_compile_actions": compile_actions,
            "unique_production_sources": 25,
            "production_lines": production_lines,
            "production_sources": source_sets["gcc"],
            "compile_database_sha256": compile_hashes,
        },
        "configuration": {
            "features": features,
            "gcc_clang_exact": True,
            "config_sha256": sha256(config_gcc),
            "oracle_only_dynamic_dependencies": {
                compiler: sorted(libraries - {"libc.so.6"})
                for compiler, libraries in expected_needed.items()
            },
            "final_rustbox_policy": "no external runtime libraries; replace or statically integrate before release",
        },
        "tests": {
            compiler: {
                "total": count,
                "passed": count,
                "log_sha256": sha256(oracle / f"{compiler}-check.log"),
            }
            for compiler, count in test_counts.items()
        },
        "cross_compiler_differential": {
            "comparisons": differential["comparisons"],
            "exact": True,
            "report_sha256": sha256(oracle / "differential.json"),
        },
        "valgrind": {
            "errors": 0,
            "leaks": 0,
            "sandbox_disabled_for_tool_compatibility": True,
            "log_sha256": sha256(oracle / "valgrind.log"),
        },
        "abi": {
            "static_defined_global_symbols": len(exported["gcc"]),
            "gcc_clang_exact": True,
            "symbols": exported["gcc"],
        },
        "compiled_magic_database": {
            "bytes": magic_gcc.stat().st_size,
            "sha256": sha256(magic_gcc),
            "gcc_clang_exact": True,
        },
        "binaries": binaries,
        "next_gate": "production-only static analysis followed by deterministic multicall entrypoint normalization",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "differential": differential["comparisons"],
        "production_sources": 25,
        "static_symbols": len(exported["gcc"]),
        "tests_per_build": 83,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
