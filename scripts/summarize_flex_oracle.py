#!/usr/bin/env python3
"""Validate and record evidence for the signed canonical Flex oracle."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "work/analysis/flex-2.6.4/oracle"
SOURCE = ROOT / "work/upstream/flex-2.6.4"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def needed(path: Path) -> list[str]:
    text = subprocess.run(
        ["readelf", "-d", str(path)], check=True, text=True,
        stdout=subprocess.PIPE,
    ).stdout
    return sorted(set(re.findall(r"Shared library: \[([^]]+)\]", text)))


def normalized_manifest(compiler: str) -> list[str]:
    root = ANALYSIS / f"{compiler}-root"
    prefix = str(root)
    return [
        line.removeprefix(prefix)
        for line in (ANALYSIS / f"{compiler}-installed-files.txt").read_text().splitlines()
    ]


def suite(compiler: str) -> dict[str, object]:
    path = ANALYSIS / f"{compiler}-check.log"
    text = path.read_text(errors="replace")
    counts = {}
    for label in ("TOTAL", "PASS", "SKIP", "XFAIL", "FAIL", "XPASS", "ERROR"):
        match = re.search(rf"^# {label}:\s+(\d+)$", text, re.MULTILINE)
        if not match:
            raise RuntimeError(f"Flex {compiler} suite lacks {label}")
        counts[label.lower()] = int(match.group(1))
    expected = {
        "total": 114, "pass": 114, "skip": 0, "xfail": 0,
        "fail": 0, "xpass": 0, "error": 0,
    }
    if counts != expected:
        raise RuntimeError(f"Flex {compiler} suite changed: {counts}")
    runtime = [line for line in text.splitlines() if "runtime error:" in line]
    address = [line for line in text.splitlines() if "ERROR: AddressSanitizer" in line]
    if runtime or address:
        raise RuntimeError(f"Flex {compiler} suite has a sanitizer diagnostic")
    return {**counts, "log_sha256": sha256(path)}


def main() -> int:
    state = json.loads((ROOT / "work/upstream/.state/flex.json").read_text())
    if not state["signature_verified"]:
        raise RuntimeError("Flex release signature is not verified")

    differential = json.loads((ANALYSIS / "differential.json").read_text())
    if differential["cases"] != 14 or differential["passed"] != 14:
        raise RuntimeError("Flex compiler differential is incomplete")
    if differential["generated_scanners"] != 10:
        raise RuntimeError("Flex generated-scanner coverage changed")

    manifests = {
        compiler: normalized_manifest(compiler)
        for compiler in ("gcc", "clang", "sanitizer")
    }
    if manifests["gcc"] != manifests["clang"] or manifests["gcc"] != manifests["sanitizer"]:
        raise RuntimeError("Flex compiler installed-file manifests differ")
    if len(manifests["gcc"]) != 40:
        raise RuntimeError("Flex installed-file surface changed")
    if "/usr/bin/flex" not in manifests["gcc"] or "/usr/bin/flex++" not in manifests["gcc"]:
        raise RuntimeError("Flex installed frontend surface changed")
    if "/usr/bin/lex" in manifests["gcc"]:
        raise RuntimeError("upstream unexpectedly installed a lex frontend")

    compile_databases = {}
    suites = {}
    for compiler in ("gcc", "clang", "sanitizer"):
        path = ANALYSIS / f"{compiler}-compile-commands.json"
        database = json.loads(path.read_text())
        sources = sorted({record["file"] for record in database})
        if len(database) != 46 or len(sources) != 24:
            raise RuntimeError(f"Flex {compiler} production closure changed")
        if sum(source.endswith("/src/stage1scan.c") for source in sources) != 1:
            raise RuntimeError(f"Flex {compiler} generated production source changed")
        if sum(source.startswith("/rustbox-flex/source/src/") for source in sources) != 23:
            raise RuntimeError(f"Flex {compiler} signed production sources changed")
        compile_databases[compiler] = {
            "commands": len(database), "sources": len(sources),
            "signed_sources": 23, "generated_sources": 1,
            "sha256": sha256(path),
        }
        suites[compiler] = suite(compiler)

    valgrind = {}
    for label in ("help", "version"):
        path = ANALYSIS / f"valgrind-{label}.log"
        text = path.read_text(errors="replace")
        required = (
            "definitely lost: 48 bytes in 1 blocks",
            "indirectly lost: 1,368 bytes in 1 blocks",
            "possibly lost: 0 bytes in 0 blocks",
        )
        if not all(item in text for item in required):
            raise RuntimeError(f"Flex {label} canonical leak signature changed")
        valgrind[label] = {
            "definitely_lost_bytes": 48,
            "indirectly_lost_bytes": 1368,
            "possibly_lost_bytes": 0,
            "log_sha256": sha256(path),
        }

    binary = ANALYSIS / "gcc-root/usr/bin/flex"
    version = subprocess.run(
        [str(binary), "--version"], check=True, text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    if version != "flex 2.6.4":
        raise RuntimeError(f"Flex version changed: {version}")
    dependencies = needed(binary)
    if any("selinux" in library or "systemd" in library for library in dependencies):
        raise RuntimeError("Flex retained a forbidden dependency")

    evidence = {
        "schema": 1,
        "release": "2.6.4",
        "recorded_at": "2026-11-22",
        "source": {**state, "entries": sum(1 for _ in SOURCE.rglob("*"))},
        "scope": {
            "canonical_installed_frontends": ["flex", "flex++"],
            "rustbox_compatibility_frontends": ["lex"],
            "c_scanners": True,
            "cxx_scanners": True,
            "java_scanners": False,
            "selinux": False,
            "systemd": False,
        },
        "installed_files": manifests["gcc"],
        "compile_databases": compile_databases,
        "upstream_suites": suites,
        "differential": differential,
        "valgrind": valgrind,
        "canonical_defects": [{
            "source": "src/main.c:flexinit",
            "diagnostic": (
                "help, version, and option-error exits bypass scanopt_destroy"
            ),
            "definitely_lost_bytes": 48,
            "indirectly_lost_bytes": 1368,
            "normalization_required": True,
        }],
        "binary": {
            "version": version,
            "bytes": binary.stat().st_size,
            "sha256": sha256(binary),
            "dynamic_needed": dependencies,
        },
    }
    output = ROOT / "evidence/flex-2.6.4-oracle.json"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "differential": differential["passed"],
        "installed_files": len(manifests["gcc"]),
        "production_sources": compile_databases["gcc"]["sources"],
        "source_entries": evidence["source"]["entries"],
        "upstream_tests_per_compiler": suites["gcc"]["pass"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
