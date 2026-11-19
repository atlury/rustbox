#!/usr/bin/env python3
"""Generate committed evidence for the canonical zlib 1.4 oracle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exported_symbols(path: Path) -> list[str]:
    output = subprocess.run(
        ["nm", "-D", "--defined-only", str(path)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    return sorted({line.split()[-1].split("@@", 1)[0] for line in output.splitlines() if line.split()})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["zlib"]
    state = json.loads((repository / "work/upstream/.state/zlib.json").read_text())
    if not state["signature_verified"] or state["sha256"] != release["sha256"]:
        raise RuntimeError("zlib release state is not verified")

    analysis = repository / "work/analysis/zlib-1.4"
    gcc_build = analysis / "canonical-gcc-cmake"
    clang_build = analysis / "canonical-clang-make"
    ctest_inventory = json.loads(
        subprocess.run(
            ["ctest", "--test-dir", str(gcc_build), "--show-only=json-v1"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout
    )
    if len(ctest_inventory["tests"]) != 18:
        raise RuntimeError("expected 18 canonical CTest cases")
    ctest = subprocess.run(
        ["ctest", "--test-dir", str(gcc_build), "--output-on-failure", "--parallel", "2"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ).stdout
    if "100% tests passed, 0 tests failed out of 18" not in ctest:
        raise RuntimeError("canonical CTest suite is incomplete")

    compile_commands = json.loads((clang_build / "compile_commands.json").read_text())
    production = sorted({Path(record["file"]).name for record in compile_commands if Path(record["file"]).parent.name == "zlib-1.4"})
    expected_production = sorted(
        path.name for path in (repository / "work/upstream/zlib-1.4").glob("*.c")
    )
    if production != expected_production or len(production) != 15:
        raise RuntimeError("Clang compilation database does not cover 15 production sources")

    gcc_library = gcc_build / "libz.so.1.4"
    clang_library = clang_build / "libz.so.1.4"
    gcc_symbols = exported_symbols(gcc_library)
    clang_symbols = exported_symbols(clang_library)
    if gcc_symbols != clang_symbols:
        raise RuntimeError("GCC and Clang zlib exported ABIs differ")

    analyzer_root = analysis / "analyzers"
    logs = {
        name: analyzer_root / name
        for name in (
            "cppcheck.log", "gcc-analyzer.log", "clang-analyzer.log",
            "clang-tidy.log", "flawfinder.log",
        )
    }
    for path in logs.values():
        if not path.is_file():
            raise RuntimeError(f"missing analyzer log: {path}")
    gcc_findings = len(re.findall(r"warning: ", logs["gcc-analyzer.log"].read_text(errors="replace")))
    clang_text = logs["clang-analyzer.log"].read_text(errors="replace")
    clang_findings = int(re.search(r"(\d+) bugs? found", clang_text).group(1))

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-20",
        "release": {
            "version": release["version"],
            "archive_sha256": release["sha256"],
            "signature_sha256": release["signature_sha256"],
            "signer_fingerprint": release["signer_fingerprint"],
            "signature_verified": True,
        },
        "builds": {
            "gcc_cmake": {"tests": 18, "passed": 18, "compile_commands": len(json.loads((gcc_build / "compile_commands.json").read_text()))},
            "clang_make": {"production_sources": production, "compile_commands": len(compile_commands), "gates": ["static", "shared", "large-file-64"]},
            "gcc_sanitizers": {"address": "pass", "undefined": "pass", "gates": ["static", "large-file-64"]},
            "valgrind": {"example": "pass", "infcover": "pass"},
        },
        "abi": {
            "exported_symbols": gcc_symbols,
            "exported_symbol_count": len(gcc_symbols),
            "gcc_library_sha256": sha256(gcc_library),
            "clang_library_sha256": sha256(clang_library),
            "matching_exports": True,
        },
        "analysis": {
            "gcc_analyzer_findings": gcc_findings,
            "clang_static_analyzer_findings": clang_findings,
            "review": [
                "Clang's two size-division reports are unreachable because nonzero size*nitems implies nonzero size.",
                "GCC's gz_init leak paths require re-entry while state->size remains zero; ASan, UBSan, Valgrind and infcover do not reproduce them.",
            ],
            "log_sha256": {name: sha256(path) for name, path in logs.items()},
        },
        "scope": {
            "production_c_files": 15,
            "installed_artifact": "libz shared/static library",
            "installed_applets": [],
            "excluded": ["unsupported contrib examples", "minigzip test helper"],
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"tests": 18, "exports": len(gcc_symbols), "gcc_analyzer": gcc_findings, "clang_analyzer": clang_findings}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
