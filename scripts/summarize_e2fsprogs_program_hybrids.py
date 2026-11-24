#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Summarize exact per-engine E2fsprogs translations and hybrid audits."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


PROGRAMS = (
    "badblocks", "chattr", "debugfs", "dumpe2fs", "e2freefrag", "e2fsck",
    "e2image", "e2initrd_helper", "e2undo", "e4crypt", "e4defrag",
    "filefrag", "fsck", "fuse2fs", "logsave", "lsattr", "mke2fs",
    "mklost_found", "resize2fs", "tune2fs",
)
PUBLIC_NAMES = (
    "badblocks", "debugfs", "dumpe2fs", "e2fsck", "e2image", "e2label",
    "e2mmpstatus", "e2undo", "fsck", "fsck.ext2", "fsck.ext3",
    "fsck.ext4", "logsave", "mke2fs", "mkfs.ext2", "mkfs.ext3",
    "mkfs.ext4", "resize2fs", "tune2fs", "chattr", "fuse2fs", "lsattr",
    "e2initrd_helper", "e2freefrag", "e4crypt", "e4defrag", "filefrag",
    "mklost+found",
)
HOLE_PATTERNS = (
    re.compile(rb"\b(?:todo|unimplemented|compile_error)!\s*\("),
    re.compile(rb"c2rust[^\n]{0,80}\b(?:hole|unimplemented)\b", re.IGNORECASE),
)
RAW_POINTER = re.compile(rb"\*(?:const|mut)\b")
THREAD_LOCAL_GATE = re.compile(rb"#!\[feature\(thread_local\)\]")
THREAD_LOCAL_ATTRIBUTE = re.compile(rb"#\[thread_local\]")
C_VARIADIC_GATE = re.compile(rb"#!\[feature\(c_variadic\)\]")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise RuntimeError(f"missing artifact: {path}")
    return {"bytes": path.stat().st_size, "sha256": sha256(path)}


def rust_inventory(directory: Path) -> dict[str, int]:
    files = sorted(directory.rglob("*.rs"))
    if not files:
        raise RuntimeError(f"no Rust sources: {directory}")
    lines = raw_pointers = holes = 0
    thread_local_gates = thread_local_attributes = c_variadic_gates = 0
    for path in files:
        data = path.read_bytes()
        lines += data.count(b"\n")
        raw_pointers += len(RAW_POINTER.findall(data))
        holes += sum(len(pattern.findall(data)) for pattern in HOLE_PATTERNS)
        thread_local_gates += len(THREAD_LOCAL_GATE.findall(data))
        thread_local_attributes += len(THREAD_LOCAL_ATTRIBUTE.findall(data))
        c_variadic_gates += len(C_VARIADIC_GATE.findall(data))
    return {
        "files": len(files),
        "lines": lines,
        "raw_pointer_type_occurrences": raw_pointers,
        "translation_holes": holes,
        "thread_local_feature_gates": thread_local_gates,
        "thread_local_attributes": thread_local_attributes,
        "c_variadic_feature_gates": c_variadic_gates,
    }


def check_valgrind(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "ERROR SUMMARY: 0 errors" not in text:
        raise RuntimeError(f"Valgrind errors: {path}")
    allocation_free = "All heap blocks were freed -- no leaks are possible" in text
    zero_losses = all(
        marker in text
        for marker in (
            "definitely lost: 0 bytes", "indirectly lost: 0 bytes",
            "possibly lost: 0 bytes",
        )
    )
    if not (allocation_free or zero_losses):
        raise RuntimeError(f"Valgrind leak result is incomplete: {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--hybrid-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    root = args.repository.resolve()
    analysis = root / "work/analysis/e2fsprogs-1.47.4"
    translations = analysis / "program-translations"
    closures_root = analysis / "program-closures/engines"
    hybrid_evidence = analysis / "program-hybrids"

    source_occurrences = 0
    unique_sources: set[str] = set()
    unique_actions: set[tuple[str, str]] = set()
    closure_counts: dict[str, int] = {}
    for name in PROGRAMS:
        closure = json.loads((closures_root / name / "closure.json").read_text())
        if closure["program"] != name:
            raise RuntimeError(f"closure identity changed: {name}")
        count = closure["source_count"]
        if count != len(closure["sources"]):
            raise RuntimeError(f"closure source count is inconsistent: {name}")
        if set(closure["compile_action_sha256"]) != set(closure["objects"]):
            raise RuntimeError(f"closure action inventory is inconsistent: {name}")
        source_occurrences += count
        closure_counts[name] = count
        unique_sources.update(closure["sources"])
        unique_actions.update(closure["compile_action_sha256"].items())
    if (source_occurrences, len(unique_sources), len(unique_actions)) != (1021, 209, 217):
        raise RuntimeError(
            "E2fsprogs aggregate closure inventory changed: "
            f"{source_occurrences}, {len(unique_sources)}, {len(unique_actions)}"
        )

    differential_path = hybrid_evidence / "differential.json"
    differential = json.loads(differential_path.read_text())
    if (
        differential.get("release") != "1.47.4"
        or differential.get("public_names") != 28
        or differential.get("engines") != 20
        or differential.get("cases") != 112
        or differential.get("passed") != 112
        or differential.get("canonical_hybrid_exact") is not True
    ):
        raise RuntimeError("E2fsprogs hybrid differential scope or result changed")
    if not all(record.get("passed") for record in differential["records"]):
        raise RuntimeError("E2fsprogs hybrid differential contains a failure")
    if {record["program"] for record in differential["records"]} != set(PUBLIC_NAMES):
        raise RuntimeError("E2fsprogs public-name differential inventory changed")
    if any(
        sum(record["program"] == name for record in differential["records"]) != 4
        for name in PUBLIC_NAMES
    ):
        raise RuntimeError("E2fsprogs public-name case coverage changed")

    records: dict[str, object] = {}
    totals = {
        "rust_files": 0,
        "raw_rust_lines": 0,
        "final_rust_lines": 0,
        "raw_pointer_type_occurrences": 0,
        "translation_holes": 0,
        "asserted_repairs": 0,
        "archive_bytes": 0,
        "raw_thread_local_feature_gates": 0,
        "final_thread_local_feature_gates": 0,
        "raw_thread_local_attributes": 0,
        "final_thread_local_attributes": 0,
        "raw_c_variadic_feature_gates": 0,
        "final_c_variadic_feature_gates": 0,
        "closure_source_occurrences": source_occurrences,
        "unique_closure_sources": len(unique_sources),
        "unique_compile_actions": len(unique_actions),
    }
    cargo_versions: set[str] = set()
    rustc_versions: set[str] = set()
    for name in PROGRAMS:
        program = translations / name
        audit = program / f"{name}-audit"
        final = program / f"{name}-final"
        raw_inventory = rust_inventory(audit)
        final_inventory = rust_inventory(final)
        if raw_inventory["files"] != final_inventory["files"]:
            raise RuntimeError(f"Rust source count changed during {name} repair")
        if raw_inventory["raw_pointer_type_occurrences"] != final_inventory[
            "raw_pointer_type_occurrences"
        ]:
            raise RuntimeError(f"raw-pointer inventory changed during {name} repair")
        if raw_inventory["translation_holes"] or final_inventory["translation_holes"]:
            raise RuntimeError(f"translation hole detected in {name}")

        cargo_path = final / "rustbox-cargo-check.json"
        cargo = json.loads(cargo_path.read_text())
        if cargo["exit_status"] != 0 or not cargo["build_finished_success"] or cargo["errors"]:
            raise RuntimeError(f"Rust type check failed: {name}")
        cargo_versions.add(cargo["cargo"])
        rustc_versions.add(cargo["rustc"])

        finalization_path = final / "rustbox-e2fsprogs-finalization.json"
        finalization = json.loads(finalization_path.read_text())
        if (
            finalization["program"] != name
            or finalization["repairs"] != len(finalization["changes"])
            or finalization["files"] != len({change["path"] for change in finalization["changes"]})
        ):
            raise RuntimeError(f"repair inventory is inconsistent: {name}")

        archive = translations / "cargo-target" / name / "release" / f"lib{name}_audit.a"
        hybrid = args.hybrid_root / name
        link_map = hybrid_evidence / f"{name}.map"
        symbols = hybrid_evidence / f"{name}.symbols"
        valgrind = hybrid_evidence / f"valgrind-{name}.log"
        check_valgrind(valgrind)
        if sum(
            line.split()[-1] == f"rustbox_e2fsprogs_{name}_main"
            for line in symbols.read_text().splitlines() if line.split()
        ) != 1:
            raise RuntimeError(f"hybrid entrypoint count changed: {name}")

        records[name] = {
            "closure_sources": closure_counts[name],
            "raw_translation": raw_inventory,
            "final_translation": final_inventory,
            "asserted_repairs": finalization["repairs"],
            "repair_files": finalization["files"],
            "cargo_check_sha256": sha256(cargo_path),
            "finalization_sha256": sha256(finalization_path),
            "archive": artifact(archive),
            "hybrid": artifact(hybrid),
            "link_map": artifact(link_map),
            "symbols": artifact(symbols),
            "valgrind_log_sha256": sha256(valgrind),
        }
        totals["rust_files"] += raw_inventory["files"]
        totals["raw_rust_lines"] += raw_inventory["lines"]
        totals["final_rust_lines"] += final_inventory["lines"]
        totals["raw_pointer_type_occurrences"] += raw_inventory[
            "raw_pointer_type_occurrences"
        ]
        totals["translation_holes"] += raw_inventory["translation_holes"]
        totals["asserted_repairs"] += finalization["repairs"]
        totals["archive_bytes"] += archive.stat().st_size
        totals["raw_thread_local_feature_gates"] += raw_inventory[
            "thread_local_feature_gates"
        ]
        totals["final_thread_local_feature_gates"] += final_inventory[
            "thread_local_feature_gates"
        ]
        totals["raw_thread_local_attributes"] += raw_inventory[
            "thread_local_attributes"
        ]
        totals["final_thread_local_attributes"] += final_inventory[
            "thread_local_attributes"
        ]
        totals["raw_c_variadic_feature_gates"] += raw_inventory[
            "c_variadic_feature_gates"
        ]
        totals["final_c_variadic_feature_gates"] += final_inventory[
            "c_variadic_feature_gates"
        ]

    expected_totals = {
        "rust_files": 1061,
        "raw_rust_lines": 4_171_263,
        "final_rust_lines": 4_171_288,
        "raw_pointer_type_occurrences": 401_012,
        "translation_holes": 0,
        "asserted_repairs": 25,
        "archive_bytes": 440_656_386,
        "raw_thread_local_feature_gates": 15,
        "final_thread_local_feature_gates": 15,
        "raw_thread_local_attributes": 15,
        "final_thread_local_attributes": 15,
        "raw_c_variadic_feature_gates": 16,
        "final_c_variadic_feature_gates": 20,
        "closure_source_occurrences": 1021,
        "unique_closure_sources": 209,
        "unique_compile_actions": 217,
    }
    if totals != expected_totals:
        changed = {
            key: {"actual": totals.get(key), "expected": value}
            for key, value in expected_totals.items()
            if totals.get(key) != value
        }
        raise RuntimeError(f"E2fsprogs hybrid aggregate changed: {changed}")
    result = {
        "schema": 1,
        "release": "1.47.4",
        "status": "20 exact program closures translated and hybrid-verified",
        "programs": list(PROGRAMS),
        "program_count": len(PROGRAMS),
        "public_names": list(PUBLIC_NAMES),
        "public_name_count": len(PUBLIC_NAMES),
        "totals": totals,
        "cargo_versions": sorted(cargo_versions),
        "rustc_versions": sorted(rustc_versions),
        "differential": {
            "cases": differential["cases"],
            "passed": differential["passed"],
            "sha256": sha256(differential_path),
        },
        "valgrind_paths": len(PROGRAMS),
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "programs": result["program_count"],
        "public_names": result["public_name_count"],
        "cases": result["differential"]["cases"],
        "passed": result["differential"]["passed"],
        "valgrind_paths": result["valgrind_paths"],
        **totals,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
