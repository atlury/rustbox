#!/usr/bin/env python3
"""Validate and record evidence for the signed canonical GNU Bison oracle."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "work/analysis/bison-3.8.2/oracle"
SOURCE = ROOT / "work/upstream/bison-3.8.2"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix().encode()
        if path.is_symlink():
            kind, payload = b"L", os.readlink(path).encode()
        elif path.is_file():
            kind, payload = b"F", path.read_bytes()
        elif path.is_dir():
            kind, payload = b"D", b""
        else:
            raise RuntimeError(f"unsupported source entry: {path}")
        digest.update(kind + b"\0" + relative + b"\0" + payload + b"\0")
    return digest.hexdigest()


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
    successful = re.search(r"^(\d+) tests were successful\.$", text, re.MULTILINE)
    skipped = re.search(r"^(\d+) tests were skipped\.$", text, re.MULTILINE)
    if not successful or not skipped:
        raise RuntimeError(f"Bison {compiler} suite summary is absent")
    counts = {
        "successful": int(successful.group(1)),
        "skipped": int(skipped.group(1)),
    }
    if counts != {"successful": 712, "skipped": 64}:
        raise RuntimeError(f"Bison {compiler} suite changed: {counts}")
    forbidden = (
        "ERROR: AddressSanitizer", "runtime error:",
        " tests failed", " test failed",
    )
    if any(marker in text for marker in forbidden):
        raise RuntimeError(f"Bison {compiler} suite contains a failure diagnostic")
    return {**counts, "total": 776, "log_sha256": sha256(path)}


def valgrind(label: str) -> dict[str, object]:
    path = ANALYSIS / f"valgrind-{label}.log"
    text = path.read_text(errors="replace")
    error = re.search(r"ERROR SUMMARY: (\d+) errors", text)
    if not error or int(error.group(1)) != 0:
        raise RuntimeError(f"Bison {label} Valgrind errors changed")
    values: dict[str, int] = {}
    for field, pattern in (
        ("definitely_lost_bytes", r"definitely lost: ([0-9,]+) bytes"),
        ("indirectly_lost_bytes", r"indirectly lost: ([0-9,]+) bytes"),
        ("possibly_lost_bytes", r"possibly lost: ([0-9,]+) bytes"),
    ):
        match = re.search(pattern, text)
        values[field] = 0 if not match else int(match.group(1).replace(",", ""))
    return {**values, "errors": 0, "log_sha256": sha256(path)}


def main() -> int:
    state = json.loads((ROOT / "work/upstream/.state/bison.json").read_text())
    if not state["signature_verified"]:
        raise RuntimeError("Bison release signature is not verified")

    differential = json.loads((ANALYSIS / "differential.json").read_text())
    if differential["cases"] != 12 or differential["passed"] != 12:
        raise RuntimeError("Bison compiler differential is incomplete")
    if differential["compiled_parsers"] != 5:
        raise RuntimeError("Bison compiled-parser coverage changed")

    manifests = {
        compiler: normalized_manifest(compiler)
        for compiler in ("gcc", "clang", "sanitizer")
    }
    if manifests["gcc"] != manifests["clang"] or manifests["gcc"] != manifests["sanitizer"]:
        raise RuntimeError("Bison compiler installed-file manifests differ")
    if len(manifests["gcc"]) != 200:
        raise RuntimeError("Bison installed-file surface changed")
    for required in ("/usr/bin/bison", "/usr/bin/yacc", "/usr/lib/liby.a"):
        if required not in manifests["gcc"]:
            raise RuntimeError(f"Bison installed surface lacks {required}")

    databases: dict[str, object] = {}
    suites: dict[str, object] = {}
    expected_closure = {"gcc": 164, "clang": 154, "sanitizer": 164}
    for compiler in ("gcc", "clang", "sanitizer"):
        path = ANALYSIS / f"{compiler}-compile-commands.json"
        records = json.loads(path.read_text())
        sources = sorted({record["file"] for record in records})
        liby = [
            source for source in sources
            if source.endswith("/lib/main.c") or source.endswith("/lib/yyerror.c")
        ]
        expected = expected_closure[compiler]
        if len(records) != expected or len(sources) != expected or len(liby) != 2:
            raise RuntimeError(f"Bison {compiler} compile closure changed")
        databases[compiler] = {
            "commands": len(records),
            "sources": len(sources),
            "bison_production_sources": len(sources) - len(liby),
            "liby_sources": len(liby),
            "sha256": sha256(path),
        }
        suites[compiler] = suite(compiler)

    binary = ANALYSIS / "gcc-root/usr/bin/bison"
    version = subprocess.run(
        [str(binary), "--version"], check=True, text=True,
        stdout=subprocess.PIPE,
    ).stdout.splitlines()[0]
    if version != "bison (GNU Bison) 3.8.2":
        raise RuntimeError(f"Bison version changed: {version}")
    dependencies = needed(binary)
    if any("selinux" in item or "systemd" in item for item in dependencies):
        raise RuntimeError("Bison retained a forbidden dependency")

    c_cxx_resources = [
        item for item in manifests["gcc"]
        if item.startswith("/usr/share/bison/m4sugar/")
        or item.startswith("/usr/share/bison/skeletons/")
        and not item.endswith(("d-skel.m4", "d.m4", "java-skel.m4", "java.m4",
                               "lalr1.d", "lalr1.java"))
    ]
    evidence = {
        "schema": 1,
        "release": "3.8.2",
        "recorded_at": "2026-11-23",
        "source": {
            **state,
            "entries": sum(1 for _ in SOURCE.rglob("*")),
            "tree_sha256": tree_sha256(SOURCE),
        },
        "scope": {
            "canonical_frontends": ["bison", "yacc"],
            "languages": ["C", "C++"],
            "excluded_languages": ["D", "Java"],
            "selinux": False,
            "systemd": False,
        },
        "installed_files": manifests["gcc"],
        "required_c_cxx_runtime_resources": c_cxx_resources,
        "compile_databases": databases,
        "upstream_suites": suites,
        "differential": differential,
        "valgrind": {label: valgrind(label) for label in ("help", "version")},
        "binary": {
            "version": version,
            "bytes": binary.stat().st_size,
            "sha256": sha256(binary),
            "dynamic_needed": dependencies,
        },
    }
    output = ROOT / "evidence/bison-3.8.2-oracle.json"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "differential": differential["passed"],
        "installed_files": len(manifests["gcc"]),
        "production_sources": databases["gcc"]["bison_production_sources"],
        "source_entries": evidence["source"]["entries"],
        "upstream_tests_per_compiler": suites["gcc"]["successful"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
