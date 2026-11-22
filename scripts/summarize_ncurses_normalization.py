#!/usr/bin/env python3
"""Generate committed evidence for Ncurses 6.6 normalization."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


NATIVE_NAMES = [
    "captoinfo", "clear", "infocmp", "infotocap", "tabs", "tic", "toe",
    "tput", "tset", "reset",
]
EXPECTED_ACTIONS = {"gcc": 514, "clang": 515, "sanitizer": 514}
EXPECTED_CLOSURE = "1bc8f0759a62f64488c020bf908e391bd35cc5b637959b3b837d022696609eaf"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_names(database: Path, compiler: str) -> tuple[int, list[str]]:
    records = json.loads(database.read_text())
    marker = f"/normalized-{compiler}/"
    names = sorted({record["file"].replace("\\", "/").split(marker, 1)[1]
                    for record in records})
    return len(records), names


def valgrind(path: Path) -> dict[str, object]:
    text = path.read_text(errors="replace")
    if "ERROR SUMMARY: 0 errors" not in text:
        raise RuntimeError(f"Valgrind reported an error in {path.name}")
    all_freed = "All heap blocks were freed" in text
    if not all_freed and (
        "definitely lost: 0 bytes" not in text
        or "indirectly lost: 0 bytes" not in text
    ):
        raise RuntimeError(f"Valgrind leak baseline changed in {path.name}")
    heap = re.search(
        r"total heap usage: ([\d,]+) allocs, ([\d,]+) frees, ([\d,]+) bytes allocated",
        text,
    )
    if not heap:
        raise RuntimeError(f"missing Valgrind heap summary in {path.name}")
    return {
        "allocations": int(heap[1].replace(",", "")),
        "frees": int(heap[2].replace(",", "")),
        "allocated_bytes": int(heap[3].replace(",", "")),
        "all_heap_freed": all_freed,
        "errors": 0,
        "log_sha256": sha256(path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repository = args.repository.resolve()
    normalized = repository / "work/analysis/ncurses-6.6/normalized"
    manifest_path = repository / "work/analysis/ncurses-6.6/normalization-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if (len(manifest.get("changed_sources", [])), manifest.get("entrypoints")) != (8, 7):
        raise RuntimeError("Ncurses normalization manifest changed")

    production_sources: list[str] | None = None
    compilers: dict[str, object] = {}
    for compiler in ("gcc", "clang", "sanitizer"):
        database = normalized / f"{compiler}-compile-commands.json"
        actions, sources = source_names(database, compiler)
        closure = hashlib.sha256(("\n".join(sources) + "\n").encode()).hexdigest()
        if (actions, len(sources), closure) != (
            EXPECTED_ACTIONS[compiler], 264, EXPECTED_CLOSURE
        ):
            raise RuntimeError(f"Ncurses normalized {compiler} closure changed")
        if production_sources is None:
            production_sources = sources
        elif production_sources != sources:
            raise RuntimeError("Ncurses normalized compiler closures differ")
        check = normalized / f"{compiler}-check.log"
        if check.read_text(errors="replace").count("** testing") != 33:
            raise RuntimeError(f"Ncurses normalized {compiler} header checks are incomplete")
        compilers[compiler] = {
            "compile_actions": actions,
            "production_sources": len(sources),
            "compile_database_sha256": sha256(database),
            "header_checks": 33,
            "header_check_log_sha256": sha256(check),
        }
    assert production_sources is not None

    sanitizer_log = normalized / "sanitizer-install.log"
    sanitizer_text = sanitizer_log.read_text(errors="replace")
    if "runtime error:" in sanitizer_text or "ERROR: AddressSanitizer" in sanitizer_text:
        raise RuntimeError("Ncurses normalization did not remove the sanitizer defect")

    differentials: dict[str, object] = {}
    for compiler in ("gcc", "clang"):
        path = normalized / f"{compiler}-differential.json"
        result = json.loads(path.read_text())
        if (result.get("cases"), result.get("passed")) != (27, 27):
            raise RuntimeError(f"Ncurses normalized {compiler} differential is incomplete")
        terminfo = normalized / f"{compiler}-terminfo-diff.log"
        if terminfo.stat().st_size != 0:
            raise RuntimeError(f"Ncurses normalized {compiler} terminfo tree differs")
        differentials[compiler] = {
            "cases": 27, "passed": 27, "sha256": sha256(path),
            "complete_installed_terminfo_tree_byte_identical": True,
        }

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-22",
        "release": "6.6",
        "status": "complete deterministic normalization; strict C2Rust probe next",
        "manifest": manifest,
        "manifest_sha256": sha256(manifest_path),
        "scope": {
            "production_sources": 264,
            "production_closure_sha256": EXPECTED_CLOSURE,
            "changed_sources": manifest["changed_sources"],
            "changed_source_count": 8,
            "exported_entrypoints": 7,
            "native_public_names": NATIVE_NAMES,
            "generated_config_helper": "ncursesw6-config",
        },
        "compilers": compilers,
        "behavior": {
            "canonical_differentials": differentials,
            "sanitizer": {
                "address_errors": 0, "undefined_behavior_diagnostics": 0,
                "canonical_read_entry_signed_shift_removed": True,
                "install_log_sha256": sha256(sanitizer_log),
            },
            "valgrind": {name: valgrind(normalized / f"valgrind-{name}.log")
                         for name in NATIVE_NAMES},
        },
        "translation_contract": {
            "standalone_wrappers_retained": True,
            "multicall_conditional": "RUSTBOX_MULTICALL",
            "alias_personalities": {
                "rustbox_tic_main": ["tic", "captoinfo", "infotocap"],
                "rustbox_tset_main": ["tset", "reset"],
            },
            "config_helper": "translate the generated shell helper separately; it has no C entrypoint",
        },
        "next_gate": "strict per-unit C2Rust translation probe of the exact normalized closure",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "changed_sources": 8, "differential": 54, "entrypoints": 7,
        "production_sources": 264, "ubsan": 0, "valgrind": 10,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
