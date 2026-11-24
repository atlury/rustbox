#!/usr/bin/env python3
"""Publish deterministic IPRoute2 entrypoint-normalization evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


PROGRAMS = (
    "arpd", "bridge", "ctstat", "dcb", "devlink", "dpll", "genl",
    "ifstat", "ip", "lnstat", "netshaper", "nstat", "rdma", "routel",
    "rtacct", "rtmon", "rtstat", "ss", "tc", "tipc", "vdpa",
)
NATIVE_PROGRAMS = tuple(name for name in PROGRAMS if name != "routel")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree(root: Path, *, exclude_manifest: bool = False) -> dict[str, str]:
    result = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = str(path.relative_to(root))
        if exclude_manifest and relative == ".rustbox-normalization.json":
            continue
        result[relative] = sha256(path)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.repository.resolve()
    canonical = root / "work/upstream/iproute2-7.3.0"
    normalized = root / "work/normalized/iproute2-7.3.0"
    analysis = root / "work/analysis/iproute2-7.3.0/normalized"
    manifest_path = normalized / ".rustbox-normalization.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("engines") != 18 or len(manifest.get("transformations", [])) != 22:
        raise RuntimeError("IPRoute2 normalization manifest changed")

    canonical_tree = tree(canonical)
    normalized_tree = tree(normalized, exclude_manifest=True)
    if canonical_tree.keys() != normalized_tree.keys():
        raise RuntimeError("IPRoute2 normalization changed the source file set")
    changed = sorted(
        relative for relative in canonical_tree
        if canonical_tree[relative] != normalized_tree[relative]
    )
    expected_changed = sorted({item["path"] for item in manifest["transformations"]})
    if changed != expected_changed or len(changed) != 20:
        raise RuntimeError(f"IPRoute2 normalization scope changed: {changed}")

    compile_databases = {}
    for compiler, build in (
        ("gcc", Path("/rustbox-iproute2/normalized-gcc")),
        ("clang-18", Path("/rustbox-iproute2/normalized-clang-18")),
    ):
        path = analysis / f"{compiler}-compile-commands.json"
        records = json.loads(path.read_text())
        sources = {
            str((Path(record["directory"]) / record["file"]).resolve().relative_to(build))
            for record in records
        }
        expected_actions = 264 if compiler == "gcc" else 272
        if len(records) != expected_actions or len(sources) != 264:
            raise RuntimeError(f"normalized IPRoute2 {compiler} compile closure changed")
        compile_databases[compiler] = {
            "compile_actions": len(records),
            "sources": len(sources),
            "sha256": sha256(path),
        }

    differential = {}
    for compiler in ("gcc", "clang-18"):
        path = analysis / f"{compiler}-differential.json"
        result = json.loads(path.read_text())
        if (
            result.get("programs") != 21
            or result.get("cases") != 63
            or result.get("passed") != 63
            or not all(record.get("passed") for record in result.get("records", []))
        ):
            raise RuntimeError(f"normalized IPRoute2 {compiler} differential changed")
        differential[compiler] = {"cases": 63, "passed": 63, "sha256": sha256(path)}

    tests = {}
    for compiler in ("gcc", "clang-18"):
        path = analysis / f"{compiler}-privileged-test.log"
        text = path.read_text(errors="replace")
        passes = len(re.findall(r"PASS", text))
        failures = len(re.findall(r"FAILED", text))
        if (
            (analysis / f"{compiler}-privileged-test.status").read_text().strip() != "0"
            or passes != 18
            or failures != 1
            or "Running ip/link/add_type_bareudp.t" not in text
        ):
            raise RuntimeError(f"normalized IPRoute2 {compiler} upstream result changed")
        tests[compiler] = {
            "tests": 19,
            "passed": 18,
            "environmental_failures": 1,
            "sha256": sha256(path),
        }

    valgrind = {}
    for name in NATIVE_PROGRAMS:
        path = analysis / f"valgrind-{name}.log"
        if "ERROR SUMMARY: 0 errors" not in path.read_text(errors="replace"):
            raise RuntimeError(f"normalized IPRoute2 {name} Valgrind changed")
        valgrind[name] = {"errors": 0, "sha256": sha256(path)}
    routel_path = analysis / "valgrind-routel.log"
    if "Python frontend unchanged" not in routel_path.read_text():
        raise RuntimeError("normalized IPRoute2 routel marker changed")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-24",
        "release": "7.3.0",
        "status": "deterministic IPRoute2 entrypoint normalization complete",
        "scope": {
            "public_names": 21,
            "exported_native_engines": 18,
            "aliases": {"ctstat": "lnstat", "rtstat": "lnstat"},
            "unchanged_script_frontends": ["routel"],
            "source_files": len(canonical_tree),
            "changed_files": changed,
            "added_files": [],
            "removed_files": [],
        },
        "normalization_manifest": {
            "sha256": sha256(manifest_path),
            "transformations": manifest["transformations"],
        },
        "compile_databases": compile_databases,
        "differential": differential,
        "upstream_tests": tests,
        "environmental_failure": "bareudp device type unavailable in Docker host kernel",
        "valgrind": {
            "native_programs": valgrind,
            "routel": {"kind": "unchanged canonical Python frontend", "sha256": sha256(routel_path)},
        },
        "next_gate": "strict no-hole C2Rust translation of the native program closures",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"engines": 18, "cases": 126, "changed_files": 20}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
