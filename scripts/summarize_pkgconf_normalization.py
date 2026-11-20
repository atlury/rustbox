#!/usr/bin/env python3
"""Generate evidence for deterministic pkgconf C normalization."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


TOOLS = ("pkgconf", "bomtool", "pccritic", "spdxtool")
ENTRYPOINTS = {
    "pkgconf": "rustbox_pkgconf_main",
    "bomtool": "rustbox_bomtool_main",
    "pccritic": "rustbox_pccritic_main",
    "spdxtool": "rustbox_spdxtool_main",
}
TARGET_PREFIXES = ("libpkgconf.a.p/", "pkgconf.p/", "bomtool.p/", "pccritic.p/", "spdxtool.p/")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def records(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


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
        if len(fields) >= 2 and len(fields[-2]) == 1 and fields[-2].isupper():
            result.add(fields[-1])
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    normalized = repository / "work/analysis/pkgconf-3.0.11/normalized"
    oracle = repository / "work/analysis/pkgconf-3.0.11/oracle"
    manifest = json.loads((normalized / "normalization.json").read_text())
    expected_changed = sorted([
        "cli/main.c",
        "cli/bomtool/main.c",
        "cli/pccritic/main.c",
        "cli/spdxtool/main.c",
        "cli/spdxtool/core.c",
        "libpkgconf/bytecode.c",
    ])
    if manifest["changed_sources"] != expected_changed:
        raise RuntimeError("pkgconf normalization changed an unexpected source set")

    suites: dict[str, list[dict[str, object]]] = {
        name: records(normalized / f"{name}-testlog.json")
        for name in ("gcc", "clang", "sanitizer")
    }
    expected_tests = {"gcc": 32, "clang": 32, "sanitizer": 33}
    for name, suite in suites.items():
        if len(suite) != expected_tests[name] or any(item["result"] != "OK" for item in suite):
            raise RuntimeError(f"normalized pkgconf {name} suite is incomplete")
    if "api-oom-spdxtool" not in {item["name"] for item in suites["sanitizer"]}:
        raise RuntimeError("normalized sanitizer suite lacks allocation-failure coverage")

    closures: dict[str, dict[str, int]] = {}
    for compiler in ("gcc", "clang"):
        database = json.loads((normalized / f"{compiler}-compile-commands.json").read_text())
        production = [
            item for item in database
            if str(item.get("output", "")).startswith(TARGET_PREFIXES)
        ]
        unique = {item["file"] for item in production}
        if len(production) != 38 or len(unique) != 35:
            raise RuntimeError(f"normalized pkgconf {compiler} closure changed")
        closures[compiler] = {"compile_actions": len(production), "unique_sources": len(unique)}

    valgrind_summary = (normalized / "valgrind-test.log").read_text(errors="replace")
    for pattern in (r"^Ok:\s+32", r"^Fail:\s+0", r"^Skipped:\s+0"):
        if not re.search(pattern, valgrind_summary, re.MULTILINE):
            raise RuntimeError("normalized pkgconf Valgrind suite is incomplete")
    valgrind_full = (normalized / "valgrind-testlog.txt").read_text(errors="replace")
    if len(re.findall(r"ERROR SUMMARY: 0 errors", valgrind_full)) != 32:
        raise RuntimeError("normalized pkgconf Valgrind logs are incomplete")
    if re.search(r"(?:definitely|indirectly|possibly) lost: [1-9]", valgrind_full):
        raise RuntimeError("normalized pkgconf Valgrind reports lost memory")

    binaries: dict[str, dict[str, object]] = {}
    public_surface: dict[str, dict[str, str]] = {}
    for compiler in ("gcc", "clang"):
        for tool in TOOLS:
            binary = normalized / f"{tool}-{compiler}"
            exported = symbols(binary)
            if "main" not in exported or ENTRYPOINTS[tool] not in exported:
                raise RuntimeError(f"{tool}-{compiler} lacks standalone or multicall entrypoint")
            needed_text = subprocess.run(
                ["readelf", "-d", str(binary)],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout
            needed = re.findall(r"Shared library: \[([^]]+)\]", needed_text)
            if needed != ["libc.so.6"]:
                raise RuntimeError(f"unexpected normalized dependency set: {tool}-{compiler} {needed}")
            binaries[f"{tool}-{compiler}"] = {
                "bytes": binary.stat().st_size,
                "sha256": sha256(binary),
                "needed": needed,
                "entrypoint": ENTRYPOINTS[tool],
            }
            public_surface[f"{tool}-{compiler}"] = {}
            for mode in ("help", "version"):
                result = subprocess.run(
                    [str(binary), f"--{mode}"],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                expected_out = (oracle / f"{tool}-{compiler}.{mode}.out").read_bytes()
                expected_err = (oracle / f"{tool}-{compiler}.{mode}.err").read_bytes()
                if result.stdout != expected_out or result.stderr != expected_err:
                    raise RuntimeError(f"normalized public surface differs: {tool}-{compiler} --{mode}")
                public_surface[f"{tool}-{compiler}"][mode] = hashlib.sha256(
                    result.stdout + b"\0" + result.stderr
                ).hexdigest()

    archive_symbols = {
        variant: symbols(Path(f"/rustbox-pkgconf/{variant}/libpkgconf.a"))
        for variant in (
            "canonical-gcc-static",
            "canonical-clang-static",
            "normalized-gcc-static",
            "normalized-clang-static",
        )
    }
    reference = archive_symbols["canonical-gcc-static"]
    if len(reference) != 176 or any(value != reference for value in archive_symbols.values()):
        raise RuntimeError("normalized libpkgconf ABI differs from canonical")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-20",
        "release": "3.0.11",
        "transformation": manifest,
        "production": closures,
        "tests": {
            name: {
                "total": len(suite),
                "passed": len(suite),
                "skipped": 0,
                "log_sha256": sha256(normalized / f"{name}-testlog.json"),
            }
            for name, suite in suites.items()
        },
        "valgrind": {
            "tests": 32,
            "passed": 32,
            "zero_error_summaries": 32,
            "lost_bytes": 0,
            "summary_sha256": sha256(normalized / "valgrind-test.log"),
            "full_log_sha256": sha256(normalized / "valgrind-testlog.txt"),
        },
        "abi": {"libpkgconf_symbols": 176, "canonical_gcc_clang_normalized_exact": True},
        "entrypoints": {
            "conditional": "RUSTBOX_MULTICALL",
            "exports": ENTRYPOINTS,
            "standalone_main_retained": True,
        },
        "public_surface": public_surface,
        "binaries": binaries,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"entrypoints": 4, "tests": 97, "valgrind": 32, "abi_symbols": 176}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
