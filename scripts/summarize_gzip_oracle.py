#!/usr/bin/env python3
"""Publish authenticated canonical-oracle evidence for GNU Gzip 1.14."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


NAMES = [
    "gzip", "gunzip", "zcat", "uncompress", "gzexe", "zcmp", "zdiff",
    "zegrep", "zfgrep", "zforce", "zgrep", "zless", "zmore", "znew",
]


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def suite_summary(path: Path) -> dict[str, int]:
    text = path.read_text(errors="replace")
    summaries = []
    for match in re.finditer(
        r"# TOTAL:\s+(\d+).*?# PASS:\s+(\d+).*?# SKIP:\s+(\d+).*?"
        r"# XFAIL:\s+(\d+).*?# FAIL:\s+(\d+).*?# XPASS:\s+(\d+).*?# ERROR:\s+(\d+)",
        text, re.DOTALL,
    ):
        summaries.append(dict(zip(
            ("total", "pass", "skip", "xfail", "fail", "xpass", "error"),
            map(int, match.groups()),
        )))
    if not summaries:
        raise RuntimeError(f"missing test summary in {path}")
    return summaries[-1]


def source_name(path: str) -> str:
    marker = "/rustbox-gzip/source/"
    if marker in path:
        return path.split(marker, 1)[1]
    if path.endswith("/version.c"):
        return "<generated>/version.c"
    raise RuntimeError(f"unexpected compile source: {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--gcc-install", type=Path, required=True)
    parser.add_argument("--clang-install", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/gzip-1.14/oracle"
    source = repository / "work/upstream/gzip-1.14"
    state = json.loads((repository / "work/upstream/.state/gzip.json").read_text())
    if not state.get("signature_verified"):
        raise RuntimeError("GNU Gzip release signature is not verified")

    expected_suite = {
        "total": 30, "pass": 29, "skip": 1, "xfail": 0,
        "fail": 0, "xpass": 0, "error": 0,
    }
    suites = {
        name: suite_summary(analysis / f"{name}-check.log")
        for name in ("gcc", "clang", "sanitizer")
    }
    if any(summary != expected_suite for summary in suites.values()):
        raise RuntimeError(f"GNU Gzip test baseline changed: {suites!r}")

    databases = {}
    for compiler in ("gcc", "clang"):
        database = json.loads(
            (analysis / f"{compiler}-compile-commands.json").read_text()
        )
        databases[compiler] = sorted({source_name(record["file"]) for record in database})
    if databases["gcc"] != databases["clang"] or len(databases["gcc"]) != 69:
        raise RuntimeError("GCC and Clang production source closures differ")
    physical_sources = [name for name in databases["gcc"] if not name.startswith("<generated>")]
    source_lines = sum(
        len((source / name).read_text(errors="replace").splitlines())
        for name in physical_sources
    ) + 3

    differential_path = analysis / "differential.json"
    differential = json.loads(differential_path.read_text())
    if differential.get("cases") != 54 or differential.get("passed") != 54:
        raise RuntimeError("GNU Gzip differential suite is incomplete")

    installs = {"gcc": args.gcc_install.resolve(), "clang": args.clang_install.resolve()}
    installed = {}
    for compiler, directory in installs.items():
        names = sorted(path.name for path in directory.iterdir() if path.is_file())
        if names != sorted(NAMES) or any(not (directory / name).is_file() for name in NAMES):
            raise RuntimeError(f"incomplete {compiler} installed command surface: {names!r}")
        installed[compiler] = {
            name: {"bytes": (directory / name).stat().st_size, "sha256": sha256(directory / name)}
            for name in NAMES
        }

    valgrind = {}
    expected_heaps = {
        "compress": "total heap usage: 0 allocs, 0 frees, 0 bytes allocated",
        "decompress": "total heap usage: 3 allocs, 3 frees, 848 bytes allocated",
    }
    for operation, heap in expected_heaps.items():
        path = analysis / f"valgrind-{operation}.log"
        text = path.read_text(errors="replace")
        if (
            "ERROR SUMMARY: 0 errors" not in text
            or "All heap blocks were freed -- no leaks are possible" not in text
            or heap not in text
        ):
            raise RuntimeError(f"GNU Gzip {operation} Valgrind baseline changed")
        valgrind[operation] = {
            "errors": 0, "all_allocations_freed": True,
            "heap_summary": heap, "log_sha256": sha256(path),
        }

    needed = {}
    for compiler in ("gcc", "clang"):
        text = (analysis / f"gzip-{compiler}.dynamic").read_text()
        needed[compiler] = re.findall(r"Shared library: \[([^]]+)\]", text)
        if needed[compiler] != ["libc.so.6"]:
            raise RuntimeError(f"unexpected {compiler} Gzip dependencies: {needed[compiler]!r}")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-21",
        "release": "1.14",
        "status": "complete authenticated canonical oracle; normalization pending",
        "authentication": {
            "archive": state["archive"], "archive_sha256": state["sha256"],
            "signature_sha256": state["signature_sha256"],
            "signer_fingerprint": state["signer_fingerprint"],
            "signature_verified": True,
        },
        "installed_surface": {
            "public_names": NAMES, "count": len(NAMES),
            "native_binary": "gzip",
            "shell_wrappers": [name for name in NAMES if name not in ("gzip", "uncompress")],
            "hardlink_alias": {"uncompress": "gunzip"},
            "artifacts": installed,
        },
        "production_closure": {
            "translation_units": len(databases["gcc"]),
            "physical_sources": len(physical_sources),
            "source_lines": source_lines,
            "sources": databases["gcc"],
            "gcc_clang_exact": True,
        },
        "behavior": {
            "upstream_suites": suites,
            "differential": differential,
            "differential_sha256": sha256(differential_path),
            "deterministic_compressed_bytes_match": True,
            "valgrind": valgrind,
        },
        "dependencies": {
            "dynamic_needed": needed,
            "package_specific_runtime_libraries": [],
            "zless_oracle_dependency": "less 590",
            "selinux": False, "systemd": False,
        },
        "next_gate": "static analysis and deterministic C normalization of the exact production closure",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "commands": len(NAMES), "differential": differential["passed"],
        "sources": len(databases["gcc"]), "upstream_passes": suites["gcc"]["pass"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
