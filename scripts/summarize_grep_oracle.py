#!/usr/bin/env python3
"""Generate committed evidence for the canonical GNU Grep 3.12 oracle."""

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
    blocks = re.findall(
        r"# TOTAL:\s+(\d+).*?# PASS:\s+(\d+).*?# SKIP:\s+(\d+)"
        r".*?# XFAIL:\s+(\d+).*?# FAIL:\s+(\d+).*?# XPASS:\s+(\d+)"
        r".*?# ERROR:\s+(\d+)",
        text,
        re.DOTALL,
    )
    return [
        dict(zip(("total", "pass", "skip", "xfail", "fail", "xpass", "error"), map(int, block)))
        for block in blocks
    ]


def production_sources(database: Path, compiler: str) -> tuple[list[str], int, int]:
    records = json.loads(database.read_text())
    prefix = "/rustbox-grep/source/"
    sources: set[str] = set()
    test_sources = 0
    for record in records:
        source = str(record["file"])
        if source.startswith(prefix + "gnulib-tests/"):
            test_sources += 1
        elif source.startswith(prefix + "lib/") or source.startswith(prefix + "src/"):
            sources.add(source.removeprefix(prefix))
        elif source == f"/rustbox-grep/oracle-{compiler}/lib/colorize.c":
            sources.add("generated/lib/colorize.c")
        else:
            raise RuntimeError(f"unexpected Grep compile source {source}")
    return sorted(sources), len(records), test_sources


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    oracle = repository / "work/analysis/grep-3.12/oracle"
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["grep"]
    state = json.loads((repository / "work/upstream/.state/grep.json").read_text())
    for key in ("version", "sha256", "signature_sha256", "signer_fingerprint", "key_sha256"):
        if state.get(key) != release[key]:
            raise RuntimeError(f"GNU Grep source state changed at {key}")
    if not state["signature_verified"]:
        raise RuntimeError("GNU Grep release signature is not verified")

    expected_summaries = {
        "gcc": [
            {"total": 128, "pass": 113, "skip": 13, "xfail": 2, "fail": 0, "xpass": 0, "error": 0},
            {"total": 315, "pass": 277, "skip": 38, "xfail": 0, "fail": 0, "xpass": 0, "error": 0},
        ],
        "clang": [
            {"total": 128, "pass": 113, "skip": 13, "xfail": 2, "fail": 0, "xpass": 0, "error": 0},
            {"total": 315, "pass": 277, "skip": 38, "xfail": 0, "fail": 0, "xpass": 0, "error": 0},
        ],
        "sanitizer": [
            {"total": 127, "pass": 111, "skip": 14, "xfail": 2, "fail": 0, "xpass": 0, "error": 0},
            {"total": 315, "pass": 273, "skip": 42, "xfail": 0, "fail": 0, "xpass": 0, "error": 0},
        ],
    }
    actual_summaries = {compiler: summaries(oracle / f"{compiler}-check.log") for compiler in expected_summaries}
    if actual_summaries != expected_summaries:
        raise RuntimeError(f"GNU Grep suite totals changed: {actual_summaries}")

    source_sets: dict[str, list[str]] = {}
    compile_actions: dict[str, int] = {}
    test_compile_actions: dict[str, int] = {}
    compile_hashes: dict[str, str] = {}
    for compiler in ("gcc", "clang", "sanitizer"):
        database = oracle / f"{compiler}-compile-commands.json"
        sources, actions, test_actions = production_sources(database, compiler)
        source_sets[compiler] = sources
        compile_actions[compiler] = actions
        test_compile_actions[compiler] = test_actions
        compile_hashes[compiler] = sha256(database)
    if any(sources != source_sets["gcc"] for sources in source_sets.values()):
        raise RuntimeError("GNU Grep compiler production closures differ")
    if len(source_sets["gcc"]) != 129:
        raise RuntimeError("GNU Grep normal production closure changed")

    source_root = repository / "work/upstream/grep-3.12"
    production_lines = sum(
        len((oracle / "colorize.c" if name == "generated/lib/colorize.c" else source_root / name)
            .read_text(errors="replace").splitlines())
        for name in source_sets["gcc"]
    )
    binaries: dict[str, dict[str, object]] = {}
    for compiler in ("gcc", "clang"):
        binary = oracle / f"grep-{compiler}"
        libraries = needed(binary)
        if libraries != ["libpcre2-8.so.0", "libc.so.6"]:
            raise RuntimeError(f"unexpected Grep {compiler} dependencies: {libraries}")
        binaries[compiler] = {
            "bytes": binary.stat().st_size,
            "sha256": sha256(binary),
            "needed": libraries,
            "egrep_wrapper_sha256": sha256(oracle / f"egrep-{compiler}"),
            "fgrep_wrapper_sha256": sha256(oracle / f"fgrep-{compiler}"),
        }

    differential = json.loads((oracle / "differential.json").read_text())
    if differential["comparisons"] != 36 or not differential["gcc_clang_exact"]:
        raise RuntimeError("GNU Grep cross-compiler differential is incomplete")
    valgrind_text = (oracle / "valgrind.log").read_text(errors="replace")
    for expected in (
        "definitely lost: 0 bytes in 0 blocks",
        "indirectly lost: 0 bytes in 0 blocks",
        "possibly lost: 18,688 bytes in 11 blocks",
        "still reachable: 119,466 bytes in 39 blocks",
        "ERROR SUMMARY: 3 errors",
    ):
        if expected not in valgrind_text:
            raise RuntimeError(f"GNU Grep Valgrind baseline changed: {expected}")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-21",
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
            "executables": ["grep", "egrep", "fgrep"],
            "normal_production_sources": len(source_sets["gcc"]),
            "captured_compile_actions": compile_actions,
            "test_support_compile_actions": test_compile_actions,
            "program_sources": [name for name in source_sets["gcc"] if name.startswith("src/")],
            "gnulib_sources": [name for name in source_sets["gcc"] if name.startswith("lib/")],
            "generated_sources": [name for name in source_sets["gcc"] if name.startswith("generated/")],
            "production_lines": production_lines,
            "production_sources": source_sets["gcc"],
            "compile_database_sha256": compile_hashes,
            "colorize_selector_sha256": sha256(oracle / "colorize.c"),
        },
        "configuration": {
            "oracle_dynamic_dependencies": ["libpcre2-8.so.0", "libc.so.6"],
            "sanitizer_policy": {
                "asan": "detect_leaks=0:halt_on_error=1:allocator_may_return_null=1",
                "ubsan": "halt_on_error=1",
                "excluded_performance_case": "mb-non-UTF8-perf-Fw",
                "reason": "ten-million-record throughput case has fixed 30/500-second deadlines that instrumentation changes; matching semantics remain covered",
            },
        },
        "tests": {
            compiler: {
                "grep": totals[0],
                "gnulib": totals[1],
                "log_sha256": sha256(oracle / f"{compiler}-check.log"),
            }
            for compiler, totals in actual_summaries.items()
        },
        "cross_compiler_differential": {
            "comparisons": 36,
            "exact": True,
            "report_sha256": sha256(oracle / "differential.json"),
        },
        "valgrind": {
            "errors": 3,
            "definitely_lost_bytes": 0,
            "indirectly_lost_bytes": 0,
            "possibly_lost_bytes": 18688,
            "still_reachable_bytes": 119466,
            "log_sha256": sha256(oracle / "valgrind.log"),
            "baseline_note": "canonical Grep retains DFA/PCRE matcher allocations until process exit on this search path",
        },
        "binaries": binaries,
        "next_gate": "production-only static analysis followed by deterministic multicall-entrypoint normalization",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"differential": 36, "production_sources": 129, "utilities": 3}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
