#!/usr/bin/env python3
"""Publish deterministic Shadow entrypoint-normalization evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


PROGRAMS = (
    "chage", "chfn", "chgpasswd", "chpasswd", "chsh", "faillog",
    "getsubids", "gpasswd", "groupadd", "groupdel", "groupmod", "grpck",
    "grpconv", "grpunconv", "lastlog", "login", "newgidmap", "newgrp",
    "newuidmap", "newusers", "nologin", "passwd", "pwck", "pwconv",
    "pwunconv", "su", "useradd", "userdel", "usermod", "vipw", "sg",
    "vigr",
)


def engine(name: str) -> str:
    return "newgrp" if name == "sg" else "vipw" if name == "vigr" else name


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree(root: Path) -> dict[Path, str]:
    return {path.relative_to(root): sha256(path) for path in root.rglob("*") if path.is_file()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--gcc-root", required=True, type=Path)
    parser.add_argument("--clang-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.repository.resolve()
    canonical = root / "work/upstream/shadow-4.20.4"
    normalized = root / "work/normalized/shadow-4.20.4"
    analysis = root / "work/analysis/shadow-4.20.4/normalized"

    manifest_path = normalized / "rustbox-normalization.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("entrypoint_engines") != 30 or manifest.get("public_programs") != 32:
        raise RuntimeError("Shadow normalization manifest changed")
    canonical_tree = tree(canonical)
    normalized_tree = tree(normalized)
    added = set(normalized_tree) - set(canonical_tree)
    changed = sorted(
        str(path) for path in set(canonical_tree) & set(normalized_tree)
        if canonical_tree[path] != normalized_tree[path]
    )
    intended = sorted(set(record["path"] for record in manifest["transformations"]))
    if added != {Path("rustbox-normalization.json")} or changed != intended:
        raise RuntimeError(f"Shadow normalization scope changed: added={added}, changed={changed}")

    suites = {}
    for compiler, stem in (("gcc", "gcc"), ("clang", "clang-18")):
        path = analysis / f"{stem}-test.log"
        text = path.read_text(errors="replace")
        match = re.search(r"# TOTAL:\s+8.*?# PASS:\s+8.*?# FAIL:\s+0.*?# ERROR:\s+0", text, re.DOTALL)
        if int((analysis / f"{stem}-test.status").read_text()) != 0 or not match:
            raise RuntimeError(f"normalized Shadow {compiler} unit suite changed")
        suites[compiler] = {"passes": 8, "failures": 0, "log_sha256": sha256(path)}

    differentials = {}
    for compiler in ("gcc", "clang"):
        path = analysis / f"{compiler}-differential.json"
        report = json.loads(path.read_text())
        if report.get("cases") != 79 or report.get("passed") != 79:
            raise RuntimeError(f"normalized Shadow {compiler} differential changed")
        differentials[compiler] = {"cases": 79, "passed": 79, "sha256": sha256(path)}

    valgrind = {}
    for name in PROGRAMS:
        path = analysis / f"valgrind-{name}.log"
        text = path.read_text(errors="replace")
        if name == "gpasswd":
            if not all(marker in text for marker in (
                "ERROR SUMMARY: 6 errors from 6 contexts",
                "definitely lost: 48 bytes in 1 blocks",
                "indirectly lost: 28 bytes in 5 blocks",
            )):
                raise RuntimeError("normalized Shadow gpasswd allocation baseline changed")
            valgrind[name] = {"errors": 6, "definitely_lost_bytes": 48, "sha256": sha256(path)}
        else:
            if "ERROR SUMMARY: 0 errors" not in text:
                raise RuntimeError(f"normalized Shadow {name} Valgrind result changed")
            valgrind[name] = {"errors": 0, "sha256": sha256(path)}

    roots = {"gcc": args.gcc_root.resolve(), "clang": args.clang_root.resolve()}
    binaries = {}
    for compiler, program_root in roots.items():
        binaries[compiler] = {}
        stem = "gcc" if compiler == "gcc" else "clang-18"
        for name in PROGRAMS:
            symbol = f"rustbox_shadow_{engine(name)}_main"
            symbols = (analysis / f"{stem}-{name}.symbols").read_text()
            count = len(re.findall(rf"\b{re.escape(symbol)}$", symbols, re.MULTILINE))
            if count != 1:
                raise RuntimeError(f"normalized Shadow {compiler}/{name} entrypoint count changed")
            binary = program_root / name
            binaries[compiler][name] = {
                "bytes": binary.stat().st_size,
                "sha256": sha256(binary),
                "entrypoint": symbol,
                "entrypoint_definitions": 1,
            }

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-24",
        "status": "deterministic Shadow entrypoint normalization complete",
        "release": "4.20.4",
        "scope": {
            "changed_source_files": len(changed),
            "added_files": ["rustbox-normalization.json"],
            "entrypoint_engines": 30,
            "public_programs": 32,
            "changed_paths": changed,
        },
        "aliases": manifest["aliases"],
        "manifest_sha256": sha256(manifest_path),
        "upstream_suites": suites,
        "differentials": differentials,
        "valgrind": valgrind,
        "binaries": binaries,
        "next_gate": "strict no-hole C2Rust translation of the public Shadow production closure",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "entrypoints": 30, "programs": 32, "comparisons": 158,
        "upstream_passes": 16, "valgrind_paths": 32,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
