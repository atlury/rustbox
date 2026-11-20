#!/usr/bin/env python3
"""Generate evidence for deterministic GNU Diffutils 3.12 normalization."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


UTILITIES = ("cmp", "diff", "diff3", "sdiff")
EXPORTS = {utility: f"rustbox_{utility}_main" for utility in UTILITIES}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def needed(path: Path) -> list[str]:
    output = subprocess.run(
        ["readelf", "-d", str(path)], check=True, text=True, stdout=subprocess.PIPE
    ).stdout
    return re.findall(r"Shared library: \[([^]]+)\]", output)


def symbols(path: Path) -> set[str]:
    output = subprocess.run(
        ["nm", "-g", "--defined-only", str(path)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    return {line.split()[-1] for line in output.splitlines() if len(line.split()) >= 3}


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
    prefix = "/rustbox-diffutils/normalized-source/"
    build_prefix = f"/rustbox-diffutils/normalized-{compiler}/"
    sources: set[str] = set()
    test_sources = 0
    for record in records:
        source = str(record["file"])
        if source.startswith(prefix + "gnulib-tests/"):
            test_sources += 1
        elif source.startswith(prefix + "lib/") or source.startswith(prefix + "src/"):
            sources.add(source.removeprefix(prefix))
        elif source == build_prefix + "src/version.c":
            sources.add("generated/src/version.c")
        else:
            raise RuntimeError(f"unexpected {compiler} compile source {source}")
    return sorted(sources), len(records), test_sources


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    normalized = repository / "work/analysis/diffutils-3.12/normalized"
    oracle = repository / "work/analysis/diffutils-3.12/oracle"
    manifest = json.loads((normalized / "normalization.json").read_text())
    expected_changed = ["src/cmp.c", "src/diff.c", "src/diff3.c", "src/sdiff.c"]
    if manifest["changed_sources"] != expected_changed:
        raise RuntimeError("GNU Diffutils normalization changed an unexpected source set")
    if manifest["entrypoints"] != list(EXPORTS.values()):
        raise RuntimeError("GNU Diffutils normalized entrypoint set changed")
    if manifest["engine"] != "exact deterministic source rewrite":
        raise RuntimeError("GNU Diffutils normalization engine changed")

    expected_summaries = {
        "gcc": [
            {"total": 33, "pass": 30, "skip": 2, "xfail": 1, "fail": 0, "xpass": 0, "error": 0},
            {"total": 344, "pass": 301, "skip": 43, "xfail": 0, "fail": 0, "xpass": 0, "error": 0},
        ],
        "clang": [
            {"total": 33, "pass": 30, "skip": 2, "xfail": 1, "fail": 0, "xpass": 0, "error": 0},
            {"total": 344, "pass": 301, "skip": 43, "xfail": 0, "fail": 0, "xpass": 0, "error": 0},
        ],
        "sanitizer": [
            {"total": 33, "pass": 30, "skip": 2, "xfail": 1, "fail": 0, "xpass": 0, "error": 0},
            {"total": 344, "pass": 297, "skip": 47, "xfail": 0, "fail": 0, "xpass": 0, "error": 0},
        ],
    }
    actual_summaries = {
        compiler: summaries(normalized / f"{compiler}-check.log")
        for compiler in expected_summaries
    }
    if actual_summaries != expected_summaries:
        raise RuntimeError(f"GNU Diffutils normalized suite totals changed: {actual_summaries}")

    source_sets: dict[str, list[str]] = {}
    production: dict[str, object] = {}
    for compiler in ("gcc", "clang", "sanitizer"):
        database = normalized / f"{compiler}-compile-commands.json"
        sources, actions, test_actions = production_sources(database, compiler)
        source_sets[compiler] = sources
        production[compiler] = {
            "captured_compile_actions": actions,
            "test_support_compile_actions": test_actions,
            "production_sources": len(sources),
            "compile_database_sha256": sha256(database),
        }
    if source_sets["gcc"] != source_sets["clang"] or len(source_sets["gcc"]) != 139:
        raise RuntimeError("GNU Diffutils normalized production closure changed")
    sanitizer_extras = sorted(set(source_sets["sanitizer"]) - set(source_sets["gcc"]))
    if sanitizer_extras != ["lib/strcasecmp.c", "lib/strncasecmp.c"]:
        raise RuntimeError(f"unexpected normalized sanitizer-only sources: {sanitizer_extras}")

    differentials: dict[str, object] = {}
    for compiler in ("gcc", "clang"):
        path = normalized / f"canonical-normalized-{compiler}-differential.json"
        report = json.loads(path.read_text())
        if report["comparisons"] != 48 or not report["gcc_clang_exact"]:
            raise RuntimeError(f"GNU Diffutils {compiler} normalization differential is incomplete")
        differentials[compiler] = {
            "comparisons": 48,
            "exact": True,
            "report_sha256": sha256(path),
        }

    valgrind_expected = {
        "cmp": (0, 0, 0, 0),
        "diff": (0, 0, 0, 0),
        "diff3": (2, 4096, 0, 4096),
        "sdiff": (0, 0, 0, 0),
    }
    valgrind: dict[str, object] = {}
    for utility, expected in valgrind_expected.items():
        path = normalized / f"valgrind-{utility}.log"
        text = path.read_text(errors="replace")
        errors, definite, indirect, possible = expected
        phrases = (
            f"ERROR SUMMARY: {errors} errors",
            f"definitely lost: {definite:,} bytes",
            f"indirectly lost: {indirect:,} bytes",
            f"possibly lost: {possible:,} bytes",
        )
        if any(phrase not in text for phrase in phrases):
            raise RuntimeError(f"normalized GNU Diffutils {utility} Valgrind baseline changed")
        valgrind[utility] = {
            "errors": errors,
            "definitely_lost_bytes": definite,
            "indirectly_lost_bytes": indirect,
            "possibly_lost_bytes": possible,
            "log_sha256": sha256(path),
        }

    binaries: dict[str, object] = {}
    if (normalized / "version.c").read_bytes() != (oracle / "version.c").read_bytes():
        raise RuntimeError("normalized GNU Diffutils generated version source changed")
    for compiler in ("gcc", "clang"):
        if (normalized / f"config-{compiler}.h").read_bytes() != (oracle / f"config-{compiler}.h").read_bytes():
            raise RuntimeError(f"normalized GNU Diffutils {compiler} configuration changed")
        binaries[compiler] = {}
        for utility in UTILITIES:
            binary = normalized / f"{utility}-{compiler}"
            libraries = needed(binary)
            if libraries != ["libc.so.6"]:
                raise RuntimeError(f"normalized {utility} {compiler} dependencies changed: {libraries}")
            object_symbols = symbols(normalized / f"{utility}-{compiler}.o")
            if not {"main", EXPORTS[utility]}.issubset(object_symbols):
                raise RuntimeError(f"normalized {utility} {compiler} entrypoints are incomplete")
            binaries[compiler][utility] = {
                "bytes": binary.stat().st_size,
                "sha256": sha256(binary),
                "needed": libraries,
            }

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-20",
        "release": "3.12",
        "transformation": manifest,
        "production": {
            "by_compiler": production,
            "normal_sources": 139,
            "sanitizer_only_sources": sanitizer_extras,
            "source_set_exact_across_gcc_clang": True,
        },
        "tests": {
            compiler: {
                "diffutils": totals[0],
                "gnulib": totals[1],
                "log_sha256": sha256(normalized / f"{compiler}-check.log"),
            }
            for compiler, totals in actual_summaries.items()
        },
        "differential": {
            "by_compiler": differentials,
            "comparisons": 96,
            "canonical_normalized_exact": True,
        },
        "valgrind": {
            "results": valgrind,
            "canonical_baseline_exact": True,
        },
        "entrypoint": {
            "conditional": "RUSTBOX_MULTICALL",
            "exports": list(EXPORTS.values()),
            "standalone_main_retained": True,
            "gcc_clang_object_symbols_verified": True,
        },
        "configuration": {
            "canonical_normalized_exact_by_compiler": True,
            "generated_version_source_exact": True,
        },
        "binaries": binaries,
        "next_gate": "C2Rust audit translation of the exact 139-source normal production closure",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"differential": 96, "entrypoints": 4, "production_sources": 139}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
