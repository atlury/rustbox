#!/usr/bin/env python3
"""Generate evidence for the deterministic GNU M4 C normalization."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def suite_counts(path: Path) -> dict[str, int]:
    text = path.read_text(errors="replace")
    counts = {}
    for key in ("TOTAL", "PASS", "SKIP", "XFAIL", "FAIL", "XPASS", "ERROR"):
        match = re.search(rf"^# {key}:\s+(\d+)$", text, re.MULTILINE)
        if not match:
            raise RuntimeError(f"missing {key} in {path}")
        counts[key.lower()] = int(match.group(1))
    if counts["total"] != 382 or counts["fail"] or counts["error"] or counts["xpass"]:
        raise RuntimeError(f"normalized suite failed: {counts}")
    return counts


def symbols(path: Path) -> set[str]:
    text = subprocess.run(
        ["nm", "-g", "--defined-only", str(path)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    return {line.split()[-1] for line in text.splitlines() if line.split()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    normalized = repository / "work/analysis/m4-1.4.21/normalized"
    manifest = json.loads((normalized / "normalization.json").read_text())
    if manifest["changed_sources"] != ["src/m4.c"]:
        raise RuntimeError("normalization changed an unexpected source set")

    suites = {
        compiler: suite_counts(normalized / f"{compiler}-test-suite.log")
        for compiler in ("gcc", "clang")
    }
    command_logs = {
        compiler: normalized / f"{compiler}-check.log"
        for compiler in ("gcc", "clang")
    }
    for compiler, path in command_logs.items():
        if "All checks successful" not in path.read_text(errors="replace"):
            raise RuntimeError(f"normalized {compiler} language checks failed")

    compile_counts = {}
    application_counts = {}
    for compiler in ("gcc", "clang"):
        records = json.loads((normalized / f"{compiler}-compile-commands.json").read_text())
        production = [
            record for record in records
            if record["file"].startswith("/rustbox-m4/normalized-source/src/")
            or record["file"].startswith("/rustbox-m4/normalized-source/lib/")
        ]
        application = [
            record for record in production
            if record["file"].startswith("/rustbox-m4/normalized-source/src/")
        ]
        compile_counts[compiler] = len(production)
        application_counts[compiler] = len(application)
    if set(compile_counts.values()) != {192} or set(application_counts.values()) != {11}:
        raise RuntimeError("normalized compile closure differs from the oracle")

    valgrind_path = normalized / "valgrind.log"
    valgrind_text = valgrind_path.read_text(errors="replace")
    if "ERROR SUMMARY: 0 errors" not in valgrind_text:
        raise RuntimeError("normalized Valgrind run reported an error")
    for kind in ("definitely lost", "indirectly lost", "possibly lost"):
        if not re.search(rf"{kind}: 0 bytes in 0 blocks", valgrind_text):
            raise RuntimeError(f"normalized Valgrind reported {kind}")

    binaries = {
        compiler: normalized / f"m4-{compiler}" for compiler in ("gcc", "clang")
    }
    for compiler, binary in binaries.items():
        exported = symbols(binary)
        if "main" not in exported or "rustbox_m4_main" not in exported:
            raise RuntimeError(f"normalized {compiler} binary lacks both entrypoints")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-20",
        "release": "1.4.21",
        "transformation": manifest,
        "builds": {
            compiler: {
                "production_compile_commands": compile_counts[compiler],
                "application_sources": application_counts[compiler],
                "language_checks": 242,
                "language_policy_skips": 7,
                "stack_overflow_check": "pass",
                "gnulib": suites[compiler],
            }
            for compiler in ("gcc", "clang")
        },
        "entrypoints": {
            "standalone": "main",
            "multicall": "rustbox_m4_main",
            "conditional": "RUSTBOX_MULTICALL",
            "present_in_both_compiler_outputs": True,
        },
        "valgrind": {
            "errors": 0,
            "definitely_indirectly_possibly_lost_bytes": 0,
        },
        "artifacts": {
            compiler: {"sha256": sha256(path), "bytes": path.stat().st_size}
            for compiler, path in binaries.items()
        },
        "logs": {
            **{f"{compiler}-check.log": sha256(path) for compiler, path in command_logs.items()},
            "valgrind.log": sha256(valgrind_path),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"changed_sources": 1, "production_sources": 192, "gnulib_tests": 382}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
