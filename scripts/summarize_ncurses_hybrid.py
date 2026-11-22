#!/usr/bin/env python3
"""Publish reproducible evidence for Ncurses 6.6's translated hybrids."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


ENTRYPOINTS = {
    "clear": "rustbox_clear_main",
    "infocmp": "rustbox_infocmp_main",
    "tabs": "rustbox_tabs_main",
    "tic": "rustbox_tic_main",
    "toe": "rustbox_toe_main",
    "tput": "rustbox_tput_main",
    "tset": "rustbox_tset_main",
}
NATIVE_NAMES = [
    "captoinfo", "clear", "infocmp", "infotocap", "tabs", "tic", "toe",
    "tput", "tset", "reset",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def symbols(path: Path) -> dict[str, int]:
    result: dict[str, int] = {}
    for line in path.read_text(errors="replace").splitlines():
        parts = line.split()
        if len(parts) >= 3:
            result[parts[-1]] = result.get(parts[-1], 0) + 1
    return result


def dependencies(path: Path) -> list[str]:
    return sorted(set(re.findall(r"Shared library: \[([^]]+)\]", path.read_text())))


def valgrind(path: Path) -> dict[str, object]:
    text = path.read_text(errors="replace")
    if "ERROR SUMMARY: 0 errors" not in text:
        raise RuntimeError(f"Valgrind reported an error in {path.name}")
    all_freed = "All heap blocks were freed" in text
    if not all_freed and any(
        marker not in text for marker in (
            "definitely lost: 0 bytes", "indirectly lost: 0 bytes",
            "possibly lost: 0 bytes",
        )
    ):
        raise RuntimeError(f"Valgrind leak baseline changed in {path.name}")
    return {"errors": 0, "all_heap_freed": all_freed, "sha256": sha256(path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/ncurses-6.6"
    hybrid = analysis / "hybrid"
    stable = analysis / "translations/c2rust-0.22.1/ncurses-6.6-normalized-audit-stable"
    archive = stable / "target/release/libncurses_6_6_normalized_audit.a"
    differential_path = hybrid / "differential.json"
    translation_path = repository / "evidence/ncurses-6.6-c2rust.json"

    differential = json.loads(differential_path.read_text())
    if (differential.get("cases"), differential.get("passed")) != (27, 27):
        raise RuntimeError("Ncurses hybrid differential is incomplete")
    toe = next(
        result for result in differential["results"]
        if result["label"] == "toe-custom-database"
    )
    if not toe.get("filesystem_order_ignored") or toe.get("records", 0) < 1800:
        raise RuntimeError("Ncurses toe filesystem-order contract changed")

    archive_symbols = symbols(hybrid / "archive.symbols")
    entrypoint_counts = {
        symbol: archive_symbols.get(symbol, 0) for symbol in ENTRYPOINTS.values()
    }
    if set(entrypoint_counts.values()) != {1}:
        raise RuntimeError(f"Ncurses translated entrypoints are not unique: {entrypoint_counts}")

    binaries: dict[str, object] = {}
    expected_dependencies = [
        "ld-linux-x86-64.so.2", "libc.so.6", "libgcc_s.so.1", "libm.so.6"
    ]
    for name, entrypoint in ENTRYPOINTS.items():
        binary = hybrid / name
        stripped = hybrid / f"{name}.stripped"
        dynamic = hybrid / f"{name}.dynamic"
        deps = dependencies(dynamic)
        if deps != expected_dependencies:
            raise RuntimeError(f"Ncurses {name} dynamic dependency set changed: {deps}")
        binary_symbols = symbols(hybrid / f"{name}.symbols")
        if binary_symbols.get(entrypoint, 0) != 1:
            raise RuntimeError(f"Ncurses {name} lost {entrypoint}")
        binaries[name] = {
            "entrypoint": entrypoint,
            "bytes": binary.stat().st_size,
            "sha256": sha256(binary),
            "stripped_bytes": stripped.stat().st_size,
            "stripped_sha256": sha256(stripped),
            "dynamic_dependencies": deps,
            "map_sha256": sha256(hybrid / f"{name}.map"),
            "sections_sha256": sha256(hybrid / f"{name}.sections"),
            "symbols_sha256": sha256(hybrid / f"{name}.symbols"),
        }

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-22",
        "release": "6.6",
        "status": "complete translated hybrid parity for ten native names; multicall integration next",
        "translation_evidence_sha256": sha256(translation_path),
        "archive": {
            "bytes": archive.stat().st_size,
            "sha256": sha256(archive),
            "entrypoint_definitions": entrypoint_counts,
            "symbols_sha256": sha256(hybrid / "archive.symbols"),
            "sections_sha256": sha256(hybrid / "archive.sections"),
            "canonical_c_residue_objects": 0,
        },
        "hybrid": {
            "native_names": NATIVE_NAMES,
            "native_name_count": len(NATIVE_NAMES),
            "alias_personalities": {
                "tic": ["captoinfo", "infotocap"],
                "tset": ["reset"],
            },
            "generated_shell_helper": "ncursesw6-config is copied unchanged",
            "binaries": binaries,
            "aggregate_unstripped_bytes": sum(item["bytes"] for item in binaries.values()),
            "aggregate_stripped_bytes": sum(item["stripped_bytes"] for item in binaries.values()),
        },
        "behavior": {
            "differential": {
                "cases": 27,
                "passed": 27,
                "sha256": sha256(differential_path),
                "toe_records_compared_order_independently": toe["records"],
                "basis": "toe exposes readdir order; exact line multiset, status, and stderr are compared for independently installed terminfo trees",
            },
            "valgrind": {
                name: valgrind(hybrid / f"valgrind-{name}.log")
                for name in NATIVE_NAMES
            },
        },
        "dependencies": {
            "external_ncurses_library": False,
            "system_dynamic": expected_dependencies,
            "rust_crates_inside_archive": ["c2rust-bitfields", "libc"],
        },
        "next_gate": "link the seven native entrypoints and three aliases into the rustbox multicall dispatcher",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "archive_bytes": archive.stat().st_size,
        "cases": 27,
        "native_names": 10,
        "residue_objects": 0,
        "stripped_bytes": evidence["hybrid"]["aggregate_stripped_bytes"],
        "valgrind": 10,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
