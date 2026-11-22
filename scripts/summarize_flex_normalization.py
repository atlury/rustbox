#!/usr/bin/env python3
"""Validate and record deterministic Flex normalization evidence."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORACLE = ROOT / "work/analysis/flex-2.6.4/oracle"
NORMALIZED = ROOT / "work/analysis/flex-2.6.4/normalized"
MANIFEST = ROOT / "work/analysis/flex-2.6.4/normalization-manifest.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_manifest(base: Path, compiler: str) -> list[str]:
    root = base / f"{compiler}-root"
    return [
        line.removeprefix(str(root))
        for line in (base / f"{compiler}-installed-files.txt").read_text().splitlines()
    ]


def suite(compiler: str) -> dict[str, object]:
    path = NORMALIZED / f"{compiler}-check.log"
    text = path.read_text(errors="replace")
    counts = {}
    for label in ("TOTAL", "PASS", "SKIP", "XFAIL", "FAIL", "XPASS", "ERROR"):
        match = re.search(rf"^# {label}:\s+(\d+)$", text, re.MULTILINE)
        if not match:
            raise RuntimeError(f"normalized Flex {compiler} suite lacks {label}")
        counts[label.lower()] = int(match.group(1))
    expected = {
        "total": 114, "pass": 114, "skip": 0, "xfail": 0,
        "fail": 0, "xpass": 0, "error": 0,
    }
    if counts != expected:
        raise RuntimeError(f"normalized Flex {compiler} suite changed")
    return {**counts, "log_sha256": sha256(path)}


def main() -> int:
    oracle_evidence = json.loads((ROOT / "evidence/flex-2.6.4-oracle.json").read_text())
    manifest = json.loads(MANIFEST.read_text())
    if manifest["changed_sources"] != ["src/main.c"]:
        raise RuntimeError("Flex normalization source set changed")
    if len(manifest["transformations"]) != 2:
        raise RuntimeError("Flex normalization transformation set changed")
    if manifest["canonical_archive_sha256"] != oracle_evidence["source"]["sha256"]:
        raise RuntimeError("Flex normalization is detached from the signed oracle")

    canonical_manifest = relative_manifest(ORACLE, "gcc")
    manifests = {
        compiler: relative_manifest(NORMALIZED, compiler)
        for compiler in ("gcc", "clang")
    }
    if manifests["gcc"] != canonical_manifest or manifests["clang"] != canonical_manifest:
        raise RuntimeError("normalized Flex installed-file surface changed")

    compile_databases = {}
    suites = {}
    for compiler in ("gcc", "clang"):
        path = NORMALIZED / f"{compiler}-compile-commands.json"
        database = json.loads(path.read_text())
        sources = {record["file"] for record in database}
        if len(database) != 46 or len(sources) != 24:
            raise RuntimeError(f"normalized Flex {compiler} closure changed")
        compile_databases[compiler] = {
            "commands": len(database), "sources": len(sources),
            "sha256": sha256(path),
        }
        suites[compiler] = suite(compiler)

    differential = json.loads((NORMALIZED / "canonical-differential.json").read_text())
    if differential["cases"] != 14 or differential["passed"] != 14:
        raise RuntimeError("Flex normalization differential is incomplete")

    valgrind = {}
    for label in ("help", "version", "invalid"):
        path = NORMALIZED / f"valgrind-{label}.log"
        text = path.read_text(errors="replace")
        required = (
            "ERROR SUMMARY: 0 errors",
            "definitely lost: 0 bytes",
            "indirectly lost: 0 bytes",
            "possibly lost: 0 bytes",
        )
        if not all(item in text for item in required):
            raise RuntimeError(f"normalized Flex {label} resource result changed")
        valgrind[label] = {"errors": 0, "lost_bytes": 0,
                           "log_sha256": sha256(path)}

    binary = NORMALIZED / "gcc-root/usr/bin/flex"
    symbols = subprocess.run(
        ["nm", "-g", str(binary)], check=True, text=True,
        stdout=subprocess.PIPE,
    ).stdout.splitlines()
    if sum(line.split()[-1:] == ["rustbox_flex_main"] for line in symbols) != 1:
        raise RuntimeError("normalized Flex multicall entrypoint changed")
    if sum(line.split()[-1:] == ["main"] for line in symbols) != 1:
        raise RuntimeError("normalized Flex standalone wrapper changed")

    evidence = {
        "schema": 1,
        "release": "2.6.4",
        "recorded_at": "2026-11-23",
        "oracle_evidence_sha256": sha256(ROOT / "evidence/flex-2.6.4-oracle.json"),
        "manifest": manifest,
        "installed_files": manifests["gcc"],
        "compile_databases": compile_databases,
        "upstream_suites": suites,
        "canonical_differential": differential,
        "valgrind": valgrind,
        "entrypoints": {
            "multicall": "rustbox_flex_main",
            "standalone": "main",
            "conditional": "RUSTBOX_MULTICALL",
        },
        "binary": {
            "bytes": binary.stat().st_size,
            "sha256": sha256(binary),
        },
        "canonical_defects_removed": [{
            "source": "src/main.c:flexinit",
            "diagnostic": "three initialized scanopt early-exit leaks",
            "definitely_lost_bytes_before": 48,
            "indirectly_lost_bytes_before": 1368,
            "lost_bytes_after": 0,
        }],
    }
    output = ROOT / "evidence/flex-2.6.4-normalization.json"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "changed_sources": len(manifest["changed_sources"]),
        "differential": differential["passed"],
        "resource_paths": len(valgrind),
        "upstream_tests": sum(item["pass"] for item in suites.values()),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
