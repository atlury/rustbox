#!/usr/bin/env python3
"""Publish canonical-parity and size evidence for translated pkgconf."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


TOOLS = ("pkgconf", "bomtool", "pccritic", "spdxtool")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def section(path: Path, name: str) -> int:
    match = re.search(rf"^{re.escape(name)}\s+(\d+)\s+", path.read_text(), re.MULTILINE)
    if not match:
        raise RuntimeError(f"missing {name} in {path}")
    return int(match.group(1))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/pkgconf-3.0.11/hybrid"
    build = repository / "build/pkgconf-3.0.11-hybrid"
    binary = build / "pkgconf-hybrid"
    stripped = build / "pkgconf-hybrid.stripped"

    fixture_path = analysis / "fixture-tests.log"
    fixture = fixture_path.read_text(errors="replace")
    fixture_suites = len(re.findall(r"^== .+ ==$", fixture, re.MULTILINE))
    fixture_passes = len(re.findall(r"^PASS:", fixture, re.MULTILINE))
    fixture_skips = len(re.findall(r"^SKIP:", fixture, re.MULTILINE))
    if (fixture_suites, fixture_passes, fixture_skips) != (14, 429, 5):
        raise RuntimeError("translated pkgconf fixture suite changed")
    if re.search(r"^(?:FAIL|ERROR):", fixture, re.MULTILINE):
        raise RuntimeError("translated pkgconf fixture suite failed")

    api_path = analysis / "api-tests.log"
    api = api_path.read_text(errors="replace")
    api_executables = len(re.findall(r"^== test-api-.+ ==$", api, re.MULTILINE))
    api_checks = len(re.findall(r": PASS$", api, re.MULTILINE))
    if (api_executables, api_checks) != (16, 223) or re.search(r"FAIL|ERROR|panic", api):
        raise RuntimeError("translated pkgconf API suite failed")

    fuzz_path = analysis / "fuzz-tests.log"
    fuzz = fuzz_path.read_text().splitlines()
    if fuzz != ["parser: PASS", "solver: PASS"]:
        raise RuntimeError("translated pkgconf fuzz replay suite failed")

    differential_path = analysis / "differential.json"
    differential = json.loads(differential_path.read_text())
    if not differential["canonical_hybrid_exact"] or differential["comparisons"] != 55:
        raise RuntimeError("translated pkgconf differential suite is incomplete")

    valgrind_logs = {
        name: analysis / f"valgrind-{name}.log"
        for name in ("pkgconf", "pkg-config", "bomtool", "pccritic", "spdxtool", "api-buffer")
    }
    for name, path in valgrind_logs.items():
        text = path.read_text(errors="replace")
        if "ERROR SUMMARY: 0 errors" not in text:
            raise RuntimeError(f"pkgconf hybrid Valgrind errors: {name}")
        if "All heap blocks were freed -- no leaks are possible" not in text:
            for kind in ("definitely lost", "indirectly lost", "possibly lost"):
                if not re.search(rf"{kind}: 0 bytes in 0 blocks", text):
                    raise RuntimeError(f"pkgconf hybrid Valgrind reported {kind}: {name}")

    dynamic = (build / "pkgconf-hybrid.dynamic").read_text()
    needed = re.findall(r"Shared library: \[([^]]+)\]", dynamic)
    expected_needed = ["libm.so.6", "libgcc_s.so.1", "libc.so.6", "ld-linux-x86-64.so.2"]
    if needed != expected_needed:
        raise RuntimeError(f"unexpected pkgconf hybrid runtime dependencies: {needed!r}")

    canonical = {
        tool: build / f"{tool}.canonical-stripped" for tool in TOOLS
    }
    for path in canonical.values():
        if not path.is_file():
            raise RuntimeError(f"missing canonical size artifact: {path}")

    translation = json.loads((repository / "evidence/pkgconf-3.0.11-c2rust.json").read_text())
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-20",
        "release": "3.0.11",
        "status": "complete translated hybrid at canonical parity; multicall integration pending",
        "implementation": {
            "rust_production_sources": 35,
            "rust_files": translation["stable_translation"]["rust_files"],
            "entrypoints": [
                "rustbox_pkgconf_main",
                "rustbox_bomtool_main",
                "rustbox_pccritic_main",
                "rustbox_spdxtool_main",
            ],
            "public_names": ["pkgconf", "pkg-config", "bomtool", "pccritic", "spdxtool"],
        },
        "behavior": {
            "upstream_suites": 32,
            "fixture_suites": fixture_suites,
            "fixture_passes": fixture_passes,
            "intentional_platform_skips": fixture_skips,
            "api_executables_relinked_against_rust": api_executables,
            "api_checks": api_checks,
            "fuzz_replay_suites": 2,
            "differential": differential,
            "valgrind_smokes": len(valgrind_logs),
        },
        "size": {
            "translation_static_archive_bytes": translation["stable_translation"]["archive"]["bytes"],
            "linked_unstripped_bytes": binary.stat().st_size,
            "linked_stripped_bytes": stripped.stat().st_size,
            "canonical_four_tools_stripped_bytes": sum(path.stat().st_size for path in canonical.values()),
            "canonical_stripped_bytes": {tool: path.stat().st_size for tool, path in canonical.items()},
            "linked_sections": {
                name.removeprefix("."): section(build / "pkgconf-hybrid.sections", name)
                for name in (".text", ".rodata", ".data", ".bss")
            },
            "interpretation": "The static archive is link inventory, not release size.",
        },
        "artifacts": {
            "linked_sha256": sha256(binary),
            "stripped_sha256": sha256(stripped),
            "fixture_log_sha256": sha256(fixture_path),
            "api_log_sha256": sha256(api_path),
            "fuzz_log_sha256": sha256(fuzz_path),
            "differential_sha256": sha256(differential_path),
            "valgrind_log_sha256": {name: sha256(path) for name, path in valgrind_logs.items()},
        },
        "runtime_linkage": {
            "current_dynamic_needed": needed,
            "final_no_dt_needed_gate": "pending Rustbox-owned static runtime",
        },
        "input_evidence": {
            name: sha256(repository / f"evidence/{name}")
            for name in (
                "pkgconf-3.0.11-oracle.json",
                "pkgconf-3.0.11-normalization.json",
                "pkgconf-3.0.11-c2rust.json",
            )
        },
        "next_gate": "link all five names into the single Rustbox multicall and replay combined regressions",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "api_checks": api_checks,
                "differential": differential["comparisons"],
                "fixture_passes": fixture_passes,
                "stripped_bytes": stripped.stat().st_size,
                "text_bytes": evidence["size"]["linked_sections"]["text"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
