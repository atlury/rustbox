#!/usr/bin/env python3
"""Validate and commit evidence for the signed GNU Gawk oracle."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "work/analysis/gawk-5.4.0/oracle"
SOURCE = ROOT / "work/upstream/gawk-5.4.0"


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
    return [
        line.removeprefix(str(root))
        for line in (ANALYSIS / f"{compiler}-installed-files.txt").read_text().splitlines()
    ]


def check_suite(compiler: str) -> dict[str, object]:
    path = ANALYSIS / f"{compiler}-check.log"
    text = path.read_text(errors="replace")
    pma_diagnostic = "Segmentation fault"
    pma_command = "GAWK_PERSIST_FILE=test.pma"
    if text.count(pma_diagnostic) != 1 or text.count(pma_command) != 1:
        raise RuntimeError(f"{compiler} PMA virtualization failure set changed")
    errors = re.findall(r"^make(?:\[\d+\])?: \*\*\* \[[^]]+: ([^]]+)\] Error \d+$",
                        text, re.MULTILINE)
    if errors != ["pma", "pma-tests", "check-recursive", "check"]:
        raise RuntimeError(f"{compiler} fatal test targets changed: {errors}")
    runtime = re.findall(r"^(.+runtime error:.+)$", text, re.MULTILINE)
    differences = [line for line in text.splitlines() if " differ:" in line]
    if compiler == "sanitizer":
        expected = (
            "/rustbox-gawk/source/extension/readdir.c:309:20: runtime error: "
            "index 1 out of bounds for type 'awk_field_info [1]'"
        )
        if runtime != [expected] * 4 or differences != [
            "readdir.ok _readdir differ: char 1, line 1"
        ]:
            raise RuntimeError("Gawk sanitizer defect set changed")
    elif runtime or differences:
        raise RuntimeError(f"{compiler} suite has an unexpected diagnostic")
    return {
        "log_sha256": sha256(path),
        "pma_virtualization_failures": 1,
        "runtime_diagnostics": len(runtime),
        "output_differences": len(differences),
    }


def main() -> int:
    state = json.loads((ROOT / "work/upstream/.state/gawk.json").read_text())
    if not state["signature_verified"]:
        raise RuntimeError("Gawk release signature is not verified")
    differential = json.loads((ANALYSIS / "differential.json").read_text())
    if differential["cases"] != 26 or differential["passed"] != 26:
        raise RuntimeError("Gawk compiler differential is incomplete")

    manifests = {compiler: normalized_manifest(compiler)
                 for compiler in ("gcc", "clang", "sanitizer")}
    if manifests["gcc"] != manifests["clang"] or manifests["gcc"] != manifests["sanitizer"]:
        raise RuntimeError("Gawk compiler installed-file manifests differ")

    compile_databases = {}
    suites = {}
    for compiler in ("gcc", "clang", "sanitizer"):
        path = ANALYSIS / f"{compiler}-compile-commands.json"
        database = json.loads(path.read_text())
        sources = sorted({record["file"] for record in database})
        if len(database) != 55 or len(sources) != 55:
            raise RuntimeError(f"{compiler} compile closure changed")
        compile_databases[compiler] = {
            "commands": len(database), "sources": len(sources),
            "sha256": sha256(path),
        }
        suites[compiler] = check_suite(compiler)

    binary = ANALYSIS / "gcc-root/usr/bin/gawk"
    version = subprocess.run(
        [str(binary), "--version"], check=True, text=True,
        stdout=subprocess.PIPE,
    ).stdout.splitlines()[0]
    required = ("GNU Awk 5.4.0", "API 4.1", "PMA Avon 8-g1", "GNU MPFR 4.2.1")
    if not all(item in version for item in required):
        raise RuntimeError(f"Gawk full-feature version changed: {version}")
    dependencies = needed(binary)
    if any("selinux" in library or "systemd" in library for library in dependencies):
        raise RuntimeError("Gawk retained a forbidden dependency")

    extensions_root = ANALYSIS / "gcc-root/usr/lib/gawk"
    extensions = sorted(path.name for path in extensions_root.glob("*.so"))
    expected_extensions = [
        "filefuncs.so", "fnmatch.so", "fork.so", "inplace.so", "intdiv.so",
        "ordchr.so", "readdir.so", "readfile.so", "revoutput.so",
        "revtwoway.so", "rwarray.so", "time.so",
    ]
    if extensions != expected_extensions:
        raise RuntimeError("Gawk extension surface changed")

    valgrind = {}
    for label in ("help", "version"):
        path = ANALYSIS / f"valgrind-{label}.log"
        text = path.read_text(errors="replace")
        if "ERROR SUMMARY: 0 errors" not in text or not all(
            item in text for item in (
                "definitely lost: 0 bytes", "indirectly lost: 0 bytes",
                "possibly lost: 0 bytes",
            )
        ):
            raise RuntimeError(f"Gawk {label} Valgrind result changed")
        valgrind[label] = {"errors": 0, "log_sha256": sha256(path)}

    evidence = {
        "schema": 1,
        "release": "5.4.0",
        "recorded_at": "2026-11-22",
        "source": {**state, "entries": sum(1 for _ in SOURCE.rglob("*"))},
        "scope": {
            "public_names": ["gawk", "awk", "gawkbug"],
            "private_programs": ["grcat", "pwcat"],
            "extensions": extensions,
            "selinux": False,
            "systemd": False,
        },
        "features": {
            "dynamic_extensions": True,
            "mpfr": True,
            "persistent_malloc": True,
            "readline": True,
            "version": version,
        },
        "installed_files": manifests["gcc"],
        "compile_databases": compile_databases,
        "upstream_suites": suites,
        "canonical_defects": [
            {
                "source": "extension/readdir.c",
                "line": 309,
                "diagnostic": "index 1 out of bounds for type 'awk_field_info [1]'",
                "observations": 4,
                "normalization_required": True,
                "log_sha256": suites["sanitizer"]["log_sha256"],
            },
            {
                "source": "support/pma.c",
                "diagnostic": "second persistent-heap mapping segfaults under amd64 emulation",
                "scope": "PMA-only upstream test; native behavior retained in every build",
                "normalization_required": False,
                "log_sha256": suites["gcc"]["log_sha256"],
            },
        ],
        "differential": differential,
        "valgrind": valgrind,
        "binary": {
            "bytes": binary.stat().st_size,
            "sha256": sha256(binary),
            "dynamic_needed": dependencies,
        },
    }
    output = ROOT / "evidence/gawk-5.4.0-oracle.json"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "differential": differential["passed"],
        "extensions": len(extensions),
        "installed_files": len(manifests["gcc"]),
        "production_sources": compile_databases["gcc"]["sources"],
        "source_entries": evidence["source"]["entries"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
