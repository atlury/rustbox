#!/usr/bin/env python3
"""Generate committed evidence for the canonical GNU Diffutils 3.12 oracle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


UTILITIES = ("cmp", "diff", "diff3", "sdiff")


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
    prefix = "/rustbox-diffutils/source/"
    build_prefix = f"/rustbox-diffutils/oracle-{compiler}/"
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
    oracle = repository / "work/analysis/diffutils-3.12/oracle"
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["diffutils"]
    state = json.loads((repository / "work/upstream/.state/diffutils.json").read_text())
    for key in ("version", "sha256", "signature_sha256", "signer_fingerprint", "key_sha256"):
        if state.get(key) != release[key]:
            raise RuntimeError(f"GNU Diffutils source state changed at {key}")
    if not state["signature_verified"]:
        raise RuntimeError("GNU Diffutils release signature is not verified")

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
    actual_summaries = {compiler: summaries(oracle / f"{compiler}-check.log") for compiler in expected_summaries}
    if actual_summaries != expected_summaries:
        raise RuntimeError(f"GNU Diffutils suite totals changed: {actual_summaries}")

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
    if source_sets["gcc"] != source_sets["clang"] or len(source_sets["gcc"]) != 139:
        raise RuntimeError("GNU Diffutils normal production closure changed")
    sanitizer_extras = sorted(set(source_sets["sanitizer"]) - set(source_sets["gcc"]))
    if sanitizer_extras != ["lib/strcasecmp.c", "lib/strncasecmp.c"]:
        raise RuntimeError(f"unexpected sanitizer-only source closure: {sanitizer_extras}")

    source_root = repository / "work/upstream/diffutils-3.12"
    production_lines = 0
    for name in source_sets["gcc"]:
        path = oracle / "version.c" if name == "generated/src/version.c" else source_root / name
        production_lines += len(path.read_text(errors="replace").splitlines())

    binaries: dict[str, dict[str, object]] = {}
    for compiler in ("gcc", "clang"):
        binaries[compiler] = {}
        for utility in UTILITIES:
            binary = oracle / f"{utility}-{compiler}"
            libraries = needed(binary)
            if libraries != ["libc.so.6"]:
                raise RuntimeError(f"unexpected {utility} {compiler} dependencies: {libraries}")
            binaries[compiler][utility] = {
                "bytes": binary.stat().st_size,
                "sha256": sha256(binary),
                "needed": libraries,
            }

    differential = json.loads((oracle / "differential.json").read_text())
    if differential["comparisons"] != 48 or not differential["gcc_clang_exact"]:
        raise RuntimeError("GNU Diffutils cross-compiler differential is incomplete")
    valgrind_expected = {
        "cmp": (0, 0, 0),
        "diff": (0, 0, 0),
        "diff3": (4096, 0, 4096),
        "sdiff": (0, 0, 0),
    }
    valgrind: dict[str, object] = {}
    for utility, losses in valgrind_expected.items():
        log_path = oracle / f"valgrind-{utility}.log"
        text = log_path.read_text(errors="replace")
        labels = ("definitely", "indirectly", "possibly")
        for label, count in zip(labels, losses):
            if f"{label} lost: {count:,} bytes" not in text:
                raise RuntimeError(f"unexpected {utility} Valgrind {label} loss")
        errors = 2 if utility == "diff3" else 0
        if f"ERROR SUMMARY: {errors} errors" not in text:
            raise RuntimeError(f"unexpected {utility} Valgrind error count")
        valgrind[utility] = {
            "errors": errors,
            "definitely_lost_bytes": losses[0],
            "indirectly_lost_bytes": losses[1],
            "possibly_lost_bytes": losses[2],
            "log_sha256": sha256(log_path),
        }

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
            "executables": list(UTILITIES),
            "normal_production_sources": len(source_sets["gcc"]),
            "normal_production_compile_actions": 139,
            "captured_compile_actions": compile_actions,
            "test_support_compile_actions": test_compile_actions,
            "program_sources": [name for name in source_sets["gcc"] if name.startswith("src/")],
            "gnulib_sources": [name for name in source_sets["gcc"] if name.startswith("lib/")],
            "generated_sources": [name for name in source_sets["gcc"] if name.startswith("generated/")],
            "production_lines": production_lines,
            "production_sources": source_sets["gcc"],
            "sanitizer_only_sources": sanitizer_extras,
            "compile_database_sha256": compile_hashes,
            "version_c_sha256": sha256(oracle / "version.c"),
        },
        "configuration": {
            "oracle_dynamic_dependencies": ["libc.so.6"],
            "sanitizer_policy": {
                "asan": "detect_leaks=0:halt_on_error=1:allocator_may_return_null=1",
                "ubsan": "halt_on_error=1",
                "disabled_checker": "nonnull-attribute, solely for gnulib memchr(NULL, ..., 0) self-test",
            },
        },
        "tests": {
            compiler: {
                "diffutils": totals[0],
                "gnulib": totals[1],
                "log_sha256": sha256(oracle / f"{compiler}-check.log"),
            }
            for compiler, totals in actual_summaries.items()
        },
        "cross_compiler_differential": {
            "comparisons": 48,
            "exact": True,
            "report_sha256": sha256(oracle / "differential.json"),
        },
        "valgrind": {
            "results": valgrind,
            "diff3_baseline_note": "canonical diff3 retains two 4096-byte read_diff buffers on this comparison path",
            "sdiff_path_note": "resource check uses --help because normal comparison delegates to a child diff process; comparison behavior is covered differentially",
        },
        "binaries": binaries,
        "next_gate": "production-only static analysis followed by deterministic multicall-entrypoint normalization",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"differential": 48, "production_sources": 139, "utilities": 4}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
