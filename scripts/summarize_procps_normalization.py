#!/usr/bin/env python3
"""Publish deterministic Procps-ng entrypoint-normalization evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


PROGRAMS = (
    "free", "hugetop", "kill", "pgrep", "pidof", "pidwait", "pkill",
    "pmap", "ps", "pwdx", "skill", "slabtop", "snice", "sysctl",
    "tload", "top", "uptime", "vmstat", "w", "watch",
)
ENTRYPOINT = {
    name: (
        "rustbox_procps_pgrep_main" if name in {"pgrep", "pkill", "pidwait"}
        else "rustbox_procps_skill_main" if name in {"skill", "snice"}
        else f"rustbox_procps_{name}_main"
    )
    for name in PROGRAMS
}


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
    canonical = root / "work/upstream/procps-ng-4.0.7"
    normalized = root / "work/normalized/procps-ng-4.0.7"
    analysis = root / "work/analysis/procps-ng-4.0.7/normalized"

    manifest_path = normalized / "rustbox-normalization.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("entrypoint_engines") != 17 or manifest.get("public_programs") != 20:
        raise RuntimeError("Procps normalization manifest changed")
    canonical_tree = tree(canonical)
    normalized_tree = tree(normalized)
    added = set(normalized_tree) - set(canonical_tree)
    changed = sorted(
        str(path) for path in set(canonical_tree) & set(normalized_tree)
        if canonical_tree[path] != normalized_tree[path]
    )
    intended = sorted(record["path"] for record in manifest["transformations"])
    if added != {Path("rustbox-normalization.json")} or changed != intended:
        raise RuntimeError(f"Procps normalization scope changed: added={added}, changed={changed}")

    suites = {}
    for compiler, stem in (("gcc", "gcc"), ("clang", "clang-18")):
        path = analysis / f"{stem}-test.log"
        text = path.read_text(errors="replace")
        dejagnu = sum(map(int, re.findall(r"^# of expected passes\s+(\d+)$", text, re.MULTILINE)))
        if int((analysis / f"{stem}-test.status").read_text()) != 0 or dejagnu != 158:
            raise RuntimeError(f"normalized Procps {compiler} DejaGNU suite changed")
        match = re.search(r"# TOTAL:\s+8.*?# PASS:\s+8.*?# FAIL:\s+0.*?# ERROR:\s+0", text, re.DOTALL)
        if not match:
            raise RuntimeError(f"normalized Procps {compiler} unit suite changed")
        suites[compiler] = {"dejagnu_passes": 158, "unit_passes": 8, "log_sha256": sha256(path)}

    differentials = {}
    for compiler in ("gcc", "clang"):
        path = analysis / f"{compiler}-differential.json"
        report = json.loads(path.read_text())
        if report.get("cases") != 51 or report.get("passed") != 51:
            raise RuntimeError(f"normalized Procps {compiler} differential changed")
        differentials[compiler] = {"cases": 51, "passed": 51, "sha256": sha256(path)}

    valgrind = {}
    for name in PROGRAMS:
        path = analysis / f"valgrind-{name}.log"
        text = path.read_text(errors="replace")
        if name == "sysctl":
            if "ERROR SUMMARY: 1 errors from 1 contexts" not in text or "definitely lost: 16 bytes in 1 blocks" not in text:
                raise RuntimeError("normalized Procps sysctl allocation baseline changed")
            valgrind[name] = {"errors": 1, "definitely_lost_bytes": 16, "sha256": sha256(path)}
        else:
            if "ERROR SUMMARY: 0 errors" not in text:
                raise RuntimeError(f"normalized Procps {name} Valgrind result changed")
            valgrind[name] = {"errors": 0, "definitely_lost_bytes": 0, "sha256": sha256(path)}

    roots = {"gcc": args.gcc_root.resolve(), "clang": args.clang_root.resolve()}
    binaries = {}
    for compiler, program_root in roots.items():
        binaries[compiler] = {}
        stem = "gcc" if compiler == "gcc" else "clang-18"
        for name in PROGRAMS:
            symbols = (analysis / f"{stem}-{name}.symbols").read_text()
            count = len(re.findall(rf"\b{re.escape(ENTRYPOINT[name])}$", symbols, re.MULTILINE))
            if count != 1:
                raise RuntimeError(f"normalized Procps {compiler}/{name} entrypoint count changed")
            binary = program_root / name
            binaries[compiler][name] = {
                "bytes": binary.stat().st_size,
                "sha256": sha256(binary),
                "entrypoint": ENTRYPOINT[name],
                "entrypoint_definitions": 1,
            }

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-24",
        "status": "deterministic Procps-ng entrypoint normalization complete",
        "release": "4.0.7",
        "scope": {
            "changed_source_files": 18,
            "added_files": ["rustbox-normalization.json"],
            "entrypoint_engines": 17,
            "public_programs": 20,
            "changed_paths": changed,
        },
        "shared_dispatch": manifest["shared_dispatch"],
        "manifest_sha256": sha256(manifest_path),
        "upstream_suites": suites,
        "differentials": differentials,
        "valgrind": valgrind,
        "binaries": binaries,
        "portable_status_dispatch_actions": 34,
        "next_gate": "strict no-hole C2Rust translation of the 49-source production closure",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"entrypoints": 17, "programs": 20, "comparisons": 102, "upstream_passes": 332}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
