#!/usr/bin/env python3
"""Publish authenticated canonical-oracle evidence for Less 710."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def needed(path: Path) -> list[str]:
    text = subprocess.run(
        ["readelf", "-d", str(path)], check=True, text=True, stdout=subprocess.PIPE
    ).stdout
    return re.findall(r"Shared library: \[([^]]+)\]", text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    source = repository / "work/upstream/less-710"
    analysis = repository / "work/analysis/less-710/oracle"
    state_path = repository / "work/upstream/.state/less.json"
    state = json.loads(state_path.read_text())
    if not state.get("signature_verified"):
        raise RuntimeError("Less 710 release signature is not verified")

    expected_sources = sorted(
        path.name for path in source.glob("*.c")
        if path.name not in {"regexp.c", "scrsize.c"}
    )
    if len(expected_sources) != 38:
        raise RuntimeError(f"Less source inventory changed: {expected_sources!r}")
    compilers = {}
    for compiler in ("gcc", "clang", "sanitizer"):
        database_path = analysis / f"{compiler}-compile-commands.json"
        database = json.loads(database_path.read_text())
        sources = sorted({Path(record["file"]).name for record in database})
        if len(database) != 38 or sources != expected_sources:
            raise RuntimeError(f"Less {compiler} production closure changed")
        log = analysis / f"{compiler}-check.log"
        text = log.read_text(errors="replace")
        if text.count("RAN  19 tests with 0 errors") != 1:
            raise RuntimeError(f"Less {compiler} upstream suite is incomplete")
        if compiler == "sanitizer" and (
            "ERROR: AddressSanitizer" in text or "runtime error:" in text
        ):
            raise RuntimeError("Less sanitizer suite reported a defect")
        compilers[compiler] = {
            "compile_actions": len(database),
            "production_sources": len(sources),
            "compile_database_sha256": sha256(database_path),
            "upstream_tests": 19,
            "upstream_log_sha256": sha256(log),
        }

    differential_path = analysis / "differential.json"
    differential = json.loads(differential_path.read_text())
    if differential.get("cases") != 22 or differential.get("passed") != 22:
        raise RuntimeError("Less differential suite is incomplete")

    expected_heaps = {
        "less": {
            "heap": "total heap usage: 41 allocs, 19 frees, 64,263 bytes allocated",
            "exit": "in use at exit: 5,946 bytes in 22 blocks",
            "all_freed": False,
        },
        "lessecho": {
            "heap": "total heap usage: 1 allocs, 1 frees, 4,096 bytes allocated",
            "exit": "in use at exit: 0 bytes in 0 blocks",
            "all_freed": True,
        },
    }
    valgrind = {}
    for applet, expected in expected_heaps.items():
        log = analysis / f"valgrind-{applet}.log"
        text = log.read_text(errors="replace")
        required = ["ERROR SUMMARY: 0 errors", expected["heap"], expected["exit"]]
        if expected["all_freed"]:
            required.append("All heap blocks were freed -- no leaks are possible")
        else:
            required.extend(["definitely lost: 0 bytes", "indirectly lost: 0 bytes"])
        if any(item not in text for item in required):
            raise RuntimeError(f"Less {applet} Valgrind baseline changed")
        valgrind[applet] = {
            "errors": 0,
            "definitely_lost_bytes": 0,
            "indirectly_lost_bytes": 0,
            "all_allocations_freed": expected["all_freed"],
            "heap_summary": expected["heap"],
            "exit_summary": expected["exit"],
            "log_sha256": sha256(log),
        }

    binaries = {}
    for compiler in ("gcc", "clang"):
        binaries[compiler] = {}
        for applet in ("less", "lessecho"):
            binary = analysis / compiler / applet
            with tempfile.TemporaryDirectory(prefix="rustbox-less-strip-") as temporary:
                stripped = Path(temporary) / applet
                shutil.copy2(binary, stripped)
                subprocess.run(["strip", "--strip-all", str(stripped)], check=True)
                stripped_bytes = stripped.stat().st_size
                stripped_hash = sha256(stripped)
            dependencies = needed(binary)
            allowed_dependencies = (
                [["libtinfo.so.6", "libc.so.6"]]
                if applet == "less"
                else [["libc.so.6"], ["libtinfo.so.6", "libc.so.6"]]
            )
            if dependencies not in allowed_dependencies:
                raise RuntimeError(f"unexpected Less {compiler}/{applet} dependencies: {dependencies}")
            binaries[compiler][applet] = {
                "bytes": binary.stat().st_size,
                "sha256": sha256(binary),
                "stripped_bytes": stripped_bytes,
                "stripped_sha256": stripped_hash,
                "dynamic_needed": dependencies,
            }

    source_lines = {
        name: len((source / name).read_text(errors="replace").splitlines())
        for name in expected_sources
    }
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-22",
        "release": "710",
        "status": "complete authenticated canonical oracle; analysis and normalization pending",
        "authentication": {
            "archive": state["archive"],
            "archive_sha256": state["sha256"],
            "signature_sha256": state["signature_sha256"],
            "signer_fingerprint": state["signer_fingerprint"],
            "signature_verified": True,
            "state_sha256": sha256(state_path),
        },
        "inventory": {
            "public_names": ["less", "lessecho"],
            "public_name_count": 2,
            "private_installed_helper": "less-osc8-open",
            "removed_upstream": {
                "lesskey": "standalone program removed by canonical upstream in version 706; source parsing is built into less"
            },
            "production_sources": expected_sources,
            "production_source_count": len(expected_sources),
            "source_lines": source_lines,
            "total_source_lines": sum(source_lines.values()),
        },
        "compilers": compilers,
        "behavior": {
            "upstream_tests": {"gcc": 19, "clang": 19, "sanitizer": 19},
            "differential": differential,
            "differential_sha256": sha256(differential_path),
            "valgrind": valgrind,
        },
        "binaries": binaries,
        "configuration": {
            "regex": "POSIX",
            "terminal_library": "tinfo",
            "systemd": False,
            "selinux": False,
        },
        "next_gate": "five-analyzer audit and deterministic multicall normalization of the exact 38-source closure",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "differential": differential["passed"],
        "production_sources": len(expected_sources),
        "source_lines": sum(source_lines.values()),
        "upstream_tests_per_compiler": 19,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
