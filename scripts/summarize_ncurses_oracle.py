#!/usr/bin/env python3
"""Generate committed evidence for the canonical Ncurses 6.6 oracle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tarfile
from pathlib import Path


PUBLIC_NAMES = [
    "captoinfo", "clear", "infocmp", "infotocap", "tabs", "tic", "toe",
    "tput", "tset", "reset", "ncursesw6-config",
]
NATIVE_NAMES = PUBLIC_NAMES[:-1]
EXPECTED_ACTIONS = {"gcc": 514, "clang": 515, "sanitizer": 514}
EXPECTED_SOURCES = 264
EXPECTED_CLOSURE = "1bc8f0759a62f64488c020bf908e391bd35cc5b637959b3b837d022696609eaf"
EXPECTED_SIGNER = "19882D92DDA4C400C22C0D56CC2AF4472167BE03"
EXPECTED_ARCHIVE_MEMBERS = 1298


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_names(database: Path, compiler: str) -> tuple[int, list[str]]:
    records = json.loads(database.read_text())
    marker = f"/source-{compiler}/"
    names = sorted({record["file"].replace("\\", "/").split(marker, 1)[1]
                    for record in records})
    return len(records), names


def dynamic_needed(path: Path) -> list[str]:
    output = subprocess.run(
        ["readelf", "-d", str(path)], check=True, text=True,
        stdout=subprocess.PIPE,
    ).stdout
    return re.findall(r"Shared library: \[([^]]+)\]", output)


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
    oracle = repository / "work/analysis/ncurses-6.6/oracle"
    state_path = repository / "work/upstream/.state/ncurses.json"
    state = json.loads(state_path.read_text())
    if not state.get("signature_verified") or state.get("signer_fingerprint") != EXPECTED_SIGNER:
        raise RuntimeError("Ncurses release signature is not authenticated")
    archive = repository / ".cache/downloads/ncurses-6.6.tar.gz"
    if sha256(archive) != state["sha256"]:
        raise RuntimeError("Ncurses archive changed after authentication")
    with tarfile.open(archive, "r:gz") as stream:
        archive_members = len(stream.getmembers())
    if archive_members != EXPECTED_ARCHIVE_MEMBERS:
        raise RuntimeError(f"unexpected Ncurses archive member count: {archive_members}")

    production_sources: list[str] | None = None
    compilers: dict[str, object] = {}
    for compiler in ("gcc", "clang", "sanitizer"):
        database = oracle / f"{compiler}-compile-commands.json"
        actions, sources = source_names(database, compiler)
        closure = hashlib.sha256(("\n".join(sources) + "\n").encode()).hexdigest()
        if (actions, len(sources), closure) != (
            EXPECTED_ACTIONS[compiler], EXPECTED_SOURCES, EXPECTED_CLOSURE
        ):
            raise RuntimeError(f"Ncurses {compiler} production closure changed")
        if production_sources is None:
            production_sources = sources
        elif production_sources != sources:
            raise RuntimeError("Ncurses compiler production closures differ")
        check = oracle / f"{compiler}-check.log"
        if check.read_text(errors="replace").count("** testing") != 33:
            raise RuntimeError(f"Ncurses {compiler} header checks are incomplete")
        compilers[compiler] = {
            "compile_actions": actions,
            "production_sources": len(sources),
            "compile_database_sha256": sha256(database),
            "header_checks": 33,
            "header_check_log_sha256": sha256(check),
            "installed_files": len((oracle / f"{compiler}-installed-files.txt").read_text().splitlines()),
        }
    assert production_sources is not None

    sanitizer_log = oracle / "sanitizer-install.log"
    sanitizer_text = sanitizer_log.read_text(errors="replace")
    diagnostics = [line for line in sanitizer_text.splitlines() if "runtime error:" in line]
    expected_ub = "read_entry.c:92:24: runtime error: left shift of 255 by 24 places"
    if not diagnostics or any(expected_ub not in line for line in diagnostics):
        raise RuntimeError("Ncurses canonical UBSan baseline changed")

    differential_path = oracle / "differential.json"
    differential = json.loads(differential_path.read_text())
    if (differential.get("cases"), differential.get("passed")) != (27, 27):
        raise RuntimeError("Ncurses compiler differential is incomplete")
    if differential.get("public_names") != PUBLIC_NAMES:
        raise RuntimeError("Ncurses differential omitted a public name")

    expected_dependencies = {
        "captoinfo": ["libticw.so.6", "libtinfow.so.6", "libc.so.6"],
        "clear": ["libtinfow.so.6", "libc.so.6"],
        "infocmp": ["libticw.so.6", "libtinfow.so.6", "libc.so.6"],
        "infotocap": ["libticw.so.6", "libtinfow.so.6", "libc.so.6"],
        "tabs": ["libtinfow.so.6", "libc.so.6"],
        "tic": ["libticw.so.6", "libtinfow.so.6", "libc.so.6"],
        "toe": ["libticw.so.6", "libtinfow.so.6", "libc.so.6"],
        "tput": ["libtinfow.so.6", "libc.so.6"],
        "tset": ["libtinfow.so.6", "libc.so.6"],
        "reset": ["libtinfow.so.6", "libc.so.6"],
    }
    binaries: dict[str, object] = {}
    for compiler in ("gcc", "clang"):
        for name in NATIVE_NAMES:
            binary = oracle / f"{compiler}-root/usr/bin/{name}"
            dependencies = dynamic_needed(binary)
            if dependencies != expected_dependencies[name]:
                raise RuntimeError(f"Ncurses {compiler} {name} dependencies changed")
            binaries[f"{compiler}-{name}"] = {
                "bytes": binary.stat().st_size,
                "sha256": sha256(binary.resolve()),
                "dynamic_needed": dependencies,
            }

    libraries = ["libncursesw", "libpanelw", "libformw", "libmenuw", "libtinfow", "libticw"]
    for compiler in ("gcc", "clang", "sanitizer"):
        for library in libraries:
            if not (oracle / f"{compiler}-root/usr/lib/{library}.so.6.6").is_file():
                raise RuntimeError(f"Ncurses {compiler} omitted {library}")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-22",
        "release": "6.6",
        "status": "complete signed canonical oracle; deterministic normalization pending",
        "source": {
            "archive": state["archive"],
            "archive_sha256": state["sha256"],
            "signature_sha256": state["signature_sha256"],
            "signature_verified": True,
            "signer_fingerprint": state["signer_fingerprint"],
            "key_sha256": state["key_sha256"],
            "archive_members": archive_members,
            "state_sha256": sha256(state_path),
        },
        "inventory": {
            "public_names": PUBLIC_NAMES,
            "public_name_count": len(PUBLIC_NAMES),
            "native_public_names": NATIVE_NAMES,
            "config_helper": "ncursesw6-config",
            "libraries": libraries,
            "production_sources": production_sources,
            "production_source_count": len(production_sources),
            "production_closure_sha256": EXPECTED_CLOSURE,
        },
        "configuration": {
            "wide_character_abi": True,
            "shared_libraries": True,
            "static_libraries": True,
            "separate_terminfo_library": True,
            "separate_tic_library": True,
            "ada": False,
            "cxx_binding": False,
            "interactive_demo_tests": False,
            "external_gpm": False,
            "external_pcre2": False,
        },
        "compilers": compilers,
        "behavior": {
            "differential": {"cases": 27, "passed": 27,
                             "sha256": sha256(differential_path)},
            "valgrind": {name: valgrind(oracle / f"valgrind-{name}.log")
                         for name in NATIVE_NAMES},
            "canonical_ubsan_baseline": {
                "diagnostic_count": len(diagnostics),
                "diagnostic": expected_ub,
                "translation_requirement": "remove signed-shift UB while preserving compiled terminfo bytes and utility behavior",
                "log_sha256": sha256(sanitizer_log),
            },
        },
        "binaries": binaries,
        "next_gate": "five-tool static audit and deterministic normalization of the exact 264-source closure",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "differential": 27,
        "production_sources": len(production_sources),
        "public_names": len(PUBLIC_NAMES),
        "valgrind": len(NATIVE_NAMES),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
