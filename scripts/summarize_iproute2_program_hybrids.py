#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Summarize exact per-program IPRoute2 translations and hybrid audits."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


PROGRAMS = (
    "arpd", "bridge", "dcb", "devlink", "dpll", "genl", "ifstat", "ip",
    "lnstat", "netshaper", "nstat", "rdma", "rtacct", "rtmon", "ss", "tc",
    "tipc", "vdpa",
)
HOLE_PATTERNS = (
    re.compile(rb"\b(?:todo|unimplemented|compile_error)!\s*\("),
    re.compile(rb"c2rust[^\n]{0,80}\b(?:hole|unimplemented)\b", re.IGNORECASE),
)
RAW_POINTER = re.compile(rb"\*(?:const|mut)\b")


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
    for path in files:
        data = path.read_bytes()
        lines += data.count(b"\n")
        raw_pointers += len(RAW_POINTER.findall(data))
        holes += sum(len(pattern.findall(data)) for pattern in HOLE_PATTERNS)
    return {
        "files": len(files),
        "lines": lines,
        "raw_pointer_type_occurrences": raw_pointers,
        "translation_holes": holes,
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
    analysis = root / "work/analysis/iproute2-7.3.0"
    translations = analysis / "program-translations"
    closures = json.loads(
        (analysis / "program-closures/engines/closure-counts.json").read_text()
    )
    if closures["engines"] != len(PROGRAMS) or set(closures["source_counts"]) != set(PROGRAMS):
        raise RuntimeError("IPRoute2 closure inventory does not name exactly 18 engines")
    if sum(closures["source_counts"].values()) != closures["sum_of_engine_source_counts"]:
        raise RuntimeError("IPRoute2 closure occurrence total is inconsistent")
    if len(closures["sources"]) != closures["unique_sources"]:
        raise RuntimeError("IPRoute2 unique closure source total is inconsistent")

    hybrid_evidence = analysis / "program-hybrids"
    differential_path = hybrid_evidence / "differential.json"
    differential = json.loads(differential_path.read_text())
    if differential["programs"] != 18 or differential["cases"] != 54:
        raise RuntimeError("IPRoute2 differential scope changed")
    if differential["passed"] != differential["cases"] or not all(
        record["passed"] for record in differential["records"]
    ):
        raise RuntimeError("IPRoute2 hybrid differential contains a failure")

    records: dict[str, object] = {}
    totals = {
        "rust_files": 0,
        "raw_rust_lines": 0,
        "final_rust_lines": 0,
        "raw_pointer_type_occurrences": 0,
        "translation_holes": 0,
        "asserted_repairs": 0,
        "closure_source_occurrences": 0,
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
        if raw_inventory["raw_pointer_type_occurrences"] != final_inventory["raw_pointer_type_occurrences"]:
            raise RuntimeError(f"raw-pointer inventory changed during {name} repair")
        if raw_inventory["translation_holes"] or final_inventory["translation_holes"]:
            raise RuntimeError(f"translation hole detected in {name}")

        cargo_path = final / "rustbox-cargo-check.json"
        cargo = json.loads(cargo_path.read_text())
        if cargo["exit_status"] != 0 or not cargo["build_finished_success"] or cargo["errors"]:
            raise RuntimeError(f"Rust type check failed: {name}")
        cargo_versions.add(cargo["cargo"])
        rustc_versions.add(cargo["rustc"])

        finalization_path = final / "rustbox-iproute2-finalization.json"
        finalization = json.loads(finalization_path.read_text())
        if finalization["program"] != name or finalization["repairs"] != len(finalization["changes"]):
            raise RuntimeError(f"repair inventory is inconsistent: {name}")

        archive = translations / "cargo-target" / name / "release" / f"lib{name}_audit.a"
        hybrid = args.hybrid_root / name
        link_map = hybrid_evidence / f"{name}.map"
        symbols = hybrid_evidence / f"{name}.symbols"
        valgrind = hybrid_evidence / f"valgrind-{name}.log"
        check_valgrind(valgrind)
        if sum(
            line.split()[-1] == f"rustbox_iproute2_{name}_main"
            for line in symbols.read_text().splitlines() if line.split()
        ) != 1:
            raise RuntimeError(f"hybrid entrypoint count changed: {name}")

        records[name] = {
            "closure_sources": closures["source_counts"][name],
            "raw_translation": raw_inventory,
            "final_translation": final_inventory,
            "asserted_repairs": finalization["repairs"],
            "repair_files": finalization["files"],
            "cargo_check_sha256": sha256(cargo_path),
            "finalization_sha256": sha256(finalization_path),
            "archive": artifact(archive),
            "hybrid": artifact(hybrid),
            "link_map_sha256": sha256(link_map),
            "symbols_sha256": sha256(symbols),
            "valgrind_log_sha256": sha256(valgrind),
        }
        totals["rust_files"] += raw_inventory["files"]
        totals["raw_rust_lines"] += raw_inventory["lines"]
        totals["final_rust_lines"] += final_inventory["lines"]
        totals["raw_pointer_type_occurrences"] += raw_inventory["raw_pointer_type_occurrences"]
        totals["translation_holes"] += raw_inventory["translation_holes"]
        totals["asserted_repairs"] += finalization["repairs"]
        totals["closure_source_occurrences"] += closures["source_counts"][name]

    expected = {
        "rust_files": 496,
        "raw_rust_lines": 1_115_530,
        "raw_pointer_type_occurrences": 265_323,
        "translation_holes": 0,
        "asserted_repairs": 46,
        "closure_source_occurrences": 460,
    }
    for key, value in expected.items():
        if totals[key] != value:
            raise RuntimeError(f"IPRoute2 aggregate changed: {key}={totals[key]}, expected {value}")
    if totals["closure_source_occurrences"] != closures["sum_of_engine_source_counts"]:
        raise RuntimeError("summarized closure occurrence count changed")

    result = {
        "schema": 1,
        "release": "7.3.0",
        "status": "18 exact program closures translated and hybrid-verified",
        "programs": list(PROGRAMS),
        "program_count": len(PROGRAMS),
        "unique_closure_sources": closures["unique_sources"],
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
        "cases": result["differential"]["cases"],
        "passed": result["differential"]["passed"],
        "valgrind_paths": result["valgrind_paths"],
        **totals,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
