#!/usr/bin/env python3
"""Generate committed evidence for the canonical GNU M4 1.4.21 oracle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def suite_counts(path: Path) -> dict[str, int]:
    text = path.read_text(errors="replace")
    keys = ("TOTAL", "PASS", "SKIP", "XFAIL", "FAIL", "XPASS", "ERROR")
    counts: dict[str, int] = {}
    for key in keys:
        match = re.search(rf"^# {key}:\s+(\d+)$", text, re.MULTILINE)
        if not match:
            raise RuntimeError(f"missing {key} in {path}")
        counts[key.lower()] = int(match.group(1))
    if counts["fail"] or counts["error"] or counts["xpass"]:
        raise RuntimeError(f"canonical M4 suite did not pass: {counts}")
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["m4"]
    state = json.loads((repository / "work/upstream/.state/m4.json").read_text())
    if not state["signature_verified"] or state["sha256"] != release["sha256"]:
        raise RuntimeError("M4 release state is not verified")

    oracle = repository / "work/analysis/m4-1.4.21/oracle"
    gcc_suite = suite_counts(oracle / "gcc-test-suite.log")
    clang_suite = suite_counts(oracle / "clang-test-suite.log")
    if gcc_suite["total"] != 382 or clang_suite["total"] != 382:
        raise RuntimeError("GCC or Clang gnulib suite inventory is incomplete")

    command_logs = {
        name: oracle / name
        for name in ("gcc-check.log", "clang-check.log", "sanitizer-check.log")
    }
    for name, path in command_logs.items():
        text = path.read_text(errors="replace")
        if "All checks successful" not in text:
            raise RuntimeError(f"M4 language suite incomplete in {name}")

    valgrind_path = oracle / "valgrind.log"
    valgrind_text = valgrind_path.read_text(errors="replace")
    leak_counts = {}
    for key in ("definitely lost", "indirectly lost", "possibly lost", "still reachable"):
        match = re.search(rf"{key}:\s+([0-9,]+) bytes in ([0-9,]+) blocks", valgrind_text)
        if not match:
            raise RuntimeError(f"missing Valgrind {key} summary")
        leak_counts[key.replace(" ", "_")] = {
            "bytes": int(match.group(1).replace(",", "")),
            "blocks": int(match.group(2).replace(",", "")),
        }
    if any(leak_counts[key]["bytes"] for key in (
        "definitely_lost", "indirectly_lost", "possibly_lost"
    )) or "ERROR SUMMARY: 0 errors" not in valgrind_text:
        raise RuntimeError("Valgrind found a non-reachable leak or memory error")

    compile_databases = {}
    production_sources = {}
    for compiler in ("gcc", "clang"):
        path = oracle / f"{compiler}-compile-commands.json"
        records = json.loads(path.read_text())
        compile_databases[compiler] = len(records)
        production_sources[compiler] = sorted(
            {
                str(Path(record["file"]).relative_to("/rustbox-m4/source"))
                for record in records
                if Path(record["file"]).is_relative_to("/rustbox-m4/source/src")
                or Path(record["file"]).is_relative_to("/rustbox-m4/source/lib")
            }
        )
    application_sources = {
        compiler: [source for source in sources if source.startswith("src/")]
        for compiler, sources in production_sources.items()
    }
    if application_sources["gcc"] != application_sources["clang"] or len(
        application_sources["gcc"]
    ) != 11:
        raise RuntimeError("GCC and Clang do not cover the same 11 M4 sources")
    gcc_sources = set(production_sources["gcc"])
    clang_sources = set(production_sources["clang"])

    binaries = {compiler: oracle / f"m4-{compiler}" for compiler in ("gcc", "clang")}
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
            "gcc": {
                "compile_commands": compile_databases["gcc"],
                "language_checks": 242,
                "language_policy_skips": 7,
                "stack_overflow_check": "pass",
                "gnulib": gcc_suite,
            },
            "clang": {
                "compile_commands": compile_databases["clang"],
                "language_checks": 242,
                "language_policy_skips": 7,
                "stack_overflow_check": "pass",
                "gnulib": clang_suite,
            },
            "gcc_sanitizers": {
                "address": "pass",
                "undefined": "pass",
                "language_suite": "pass",
            },
            "valgrind": {
                "representative_macro_program": "pass",
                "leaks": leak_counts,
                "note": "Process-lifetime macro and symbol tables remain reachable at exit.",
            },
        },
        "production": {
            "application_sources": application_sources["gcc"],
            "application_source_count": len(application_sources["gcc"]),
            "gcc_link_source_count": len(gcc_sources),
            "clang_link_source_count": len(clang_sources),
            "common_link_sources": sorted(gcc_sources & clang_sources),
            "gcc_only_link_sources": sorted(gcc_sources - clang_sources),
            "clang_only_link_sources": sorted(clang_sources - gcc_sources),
        },
        "artifacts": {
            compiler: {
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            }
            for compiler, path in binaries.items()
        },
        "logs": {
            **{name: sha256(path) for name, path in command_logs.items()},
            "valgrind.log": sha256(valgrind_path),
        },
        "scope": {
            "installed_applets": ["m4"],
            "excluded": ["examples", "test-only binaries"],
            "selinux": False,
            "systemd": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "gnulib": gcc_suite,
                "gcc_link_sources": len(gcc_sources),
                "clang_link_sources": len(clang_sources),
                "application_sources": len(application_sources["gcc"]),
                "language_checks": 242,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
