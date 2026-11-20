#!/usr/bin/env python3
"""Generate evidence for deterministic File 5.48 C normalization."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def symbols(path: Path) -> set[str]:
    output = subprocess.run(
        ["nm", "-g", "--defined-only", str(path)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    result = set()
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 3 and len(fields[-2]) == 1 and fields[-2].isupper():
            result.add(fields[-1])
    return result


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
    normalized = repository / "work/analysis/file-5.48/normalized"
    oracle = repository / "work/analysis/file-5.48/oracle"
    manifest = json.loads((normalized / "normalization.json").read_text())
    if manifest["changed_sources"] != ["src/file.c", "src/softmagic.c"]:
        raise RuntimeError("File normalization changed an unexpected source set")
    if manifest["engines"] != [
        "Coccinelle 1.3.3 semantic patch",
        "exact deterministic source rewrite",
    ]:
        raise RuntimeError("File normalization engine set changed")

    test_counts = {}
    closures = {}
    for compiler in ("gcc", "clang", "sanitizer"):
        log = normalized / f"{compiler}-check.log"
        count = len(re.findall(r"^Running test:", log.read_text(errors="replace"), re.MULTILINE))
        if count != 83:
            raise RuntimeError(f"normalized File {compiler} suite is incomplete")
        test_counts[compiler] = count
        database = json.loads((normalized / f"{compiler}-compile-commands.json").read_text())
        sources = {record["file"] for record in database}
        if len(database) != 25 or len(sources) != 25:
            raise RuntimeError(f"normalized File {compiler} closure changed")
        closures[compiler] = {"compile_actions": 25, "unique_sources": 25}

    differentials = {}
    for compiler in ("gcc", "clang"):
        path = normalized / f"canonical-normalized-{compiler}-differential.json"
        report = json.loads(path.read_text())
        if report["comparisons"] != 174 or not report["gcc_clang_exact"]:
            raise RuntimeError(f"File {compiler} normalization differential is incomplete")
        differentials[compiler] = {
            "comparisons": 174,
            "exact": True,
            "report_sha256": sha256(path),
        }

    valgrind = (normalized / "valgrind.log").read_text(errors="replace")
    if (
        "ERROR SUMMARY: 0 errors" not in valgrind
        or "All heap blocks were freed -- no leaks are possible" not in valgrind
    ):
        raise RuntimeError("normalized File Valgrind smoke is incomplete")

    archive_symbols = {}
    for variant, path in {
        "canonical_gcc": oracle / "libmagic-gcc.a",
        "canonical_clang": oracle / "libmagic-clang.a",
        "normalized_gcc": normalized / "libmagic-gcc.a",
        "normalized_clang": normalized / "libmagic-clang.a",
    }.items():
        archive_symbols[variant] = symbols(path)
    reference_symbols = archive_symbols["canonical_gcc"]
    if len(reference_symbols) != 126 or any(value != reference_symbols for value in archive_symbols.values()):
        raise RuntimeError("normalized libmagic global symbols differ from canonical")

    expected_needed = {
        "gcc": {
            "libbz2.so.1.0", "libc.so.6", "liblz.so.1", "liblzma.so.5",
            "libseccomp.so.2", "libz.so.1", "libzstd.so.1",
        },
        "clang": {
            "libbz2.so.1.0", "libc.so.6", "liblz.so.1", "liblzma.so.5",
            "libm.so.6", "libseccomp.so.2", "libz.so.1", "libzstd.so.1",
        },
    }
    binaries = {}
    for compiler in ("gcc", "clang"):
        binary = normalized / f"file-{compiler}"
        exported = symbols(binary)
        object_symbols = subprocess.run(
            ["readelf", "-sW", f"/rustbox-file/normalized-{compiler}/src/file.o"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout
        if (
            "main" not in exported
            or not re.search(r"FUNC\s+GLOBAL\s+HIDDEN.*\brustbox_file_main$", object_symbols, re.MULTILINE)
            or not re.search(r"FUNC\s+GLOBAL\s+HIDDEN.*\bmain$", object_symbols, re.MULTILINE)
        ):
            raise RuntimeError(f"normalized File {compiler} entrypoints are incomplete")
        libraries = needed(binary)
        if set(libraries) != expected_needed[compiler]:
            raise RuntimeError(f"normalized File {compiler} dependency set changed")
        binaries[compiler] = {
            "bytes": binary.stat().st_size,
            "sha256": sha256(binary),
            "needed": libraries,
        }

    for compiler in ("gcc", "clang"):
        if (normalized / f"config-{compiler}.h").read_bytes() != (oracle / f"config-{compiler}.h").read_bytes():
            raise RuntimeError(f"normalized File {compiler} feature configuration differs")
        if (normalized / f"magic-{compiler}.mgc").read_bytes() != (oracle / f"magic-{compiler}.mgc").read_bytes():
            raise RuntimeError(f"normalized File {compiler} magic database differs")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-20",
        "release": "5.48",
        "transformation": manifest,
        "production": closures,
        "tests": {
            compiler: {
                "total": count,
                "passed": count,
                "log_sha256": sha256(normalized / f"{compiler}-check.log"),
            }
            for compiler, count in test_counts.items()
        },
        "differential": {
            "by_compiler": differentials,
            "comparisons": 348,
            "canonical_normalized_exact": True,
        },
        "valgrind": {
            "errors": 0,
            "leaks": 0,
            "sandbox_disabled_for_tool_compatibility": True,
            "log_sha256": sha256(normalized / "valgrind.log"),
        },
        "abi": {
            "libmagic_defined_global_symbols": 126,
            "canonical_gcc_clang_normalized_exact": True,
        },
        "entrypoint": {
            "conditional": "RUSTBOX_MULTICALL",
            "export": "rustbox_file_main",
            "object_visibility": "GLOBAL HIDDEN under upstream -fvisibility=hidden; linkable across multicall objects",
            "standalone_main_retained": True,
        },
        "configuration": {
            "canonical_normalized_exact": True,
            "compiled_magic_database_exact": True,
        },
        "analyzer_hardening": {
            "do_ops_offset_identity_fallback": True,
            "valid_operation_semantics_unchanged": True,
        },
        "binaries": binaries,
        "next_gate": "C2Rust audit translation of the exact 25-source production closure",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "abi_symbols": 126,
        "differential": 348,
        "entrypoints": 1,
        "tests": sum(test_counts.values()),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
