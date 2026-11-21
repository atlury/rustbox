#!/usr/bin/env python3
"""Generate committed evidence for the canonical LZ4 1.11.1 oracle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def needed(path: Path) -> list[str]:
    output = subprocess.run(
        ["readelf", "-d", str(path)], check=True, text=True, stdout=subprocess.PIPE
    ).stdout
    return re.findall(r"Shared library: \[([^]]+)\]", output)


def source_names(database: Path, compiler: str) -> tuple[int, list[str]]:
    records = json.loads(database.read_text())
    names = sorted({
        str(Path(record["file"]).resolve()).replace(
            f"/rustbox-lz4/source-{compiler}/", ""
        )
        for record in records
    })
    return len(records), names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    oracle = repository / "work/analysis/lz4-1.11.1/oracle"
    source = repository / "work/upstream/lz4-1.11.1"
    state_path = repository / "work/upstream/.state/lz4.json"
    state = json.loads(state_path.read_text())
    if not state.get("integrity_verified") or state.get("signature_verified"):
        raise RuntimeError("LZ4 checksum authentication state is incomplete or misrepresented")
    archive = repository / ".cache/downloads/lz4-1.11.1.tar.gz"
    if sha256(archive) != state["sha256"]:
        raise RuntimeError("LZ4 release archive changed after authentication")
    with tarfile.open(archive, "r:gz") as stream:
        archive_members = len(stream.getmembers())
    if archive_members != 277:
        raise RuntimeError(f"unexpected LZ4 archive member count: {archive_members}")

    expected_sources = [
        "lib/lz4.c", "lib/lz4file.c", "lib/lz4frame.c", "lib/lz4hc.c",
        "lib/xxhash.c", "programs/bench.c", "programs/lorem.c",
        "programs/lz4cli.c", "programs/lz4io.c", "programs/threadpool.c",
        "programs/timefn.c", "programs/util.c",
    ]
    compilers = {}
    check_markers = [
        "test lz4 basic compression/decompression", "test command line options",
        "test --list", "test lz4 multithreaded compression",
    ]
    for compiler in ("gcc", "clang", "sanitizer"):
        database = oracle / f"{compiler}-compile-commands.json"
        actions, sources = source_names(database, compiler)
        if actions != 24 or sources != expected_sources:
            raise RuntimeError(f"LZ4 {compiler} production closure changed: {actions}, {sources}")
        log = oracle / f"{compiler}-check.log"
        text = log.read_text(errors="replace")
        if "make: ***" in text or any(marker not in text for marker in check_markers):
            raise RuntimeError(f"LZ4 {compiler} upstream essentials suite is incomplete")
        if compiler == "sanitizer" and (
            "ERROR: AddressSanitizer" in text
            or re.search(r"\.c:\d+(?::\d+)?: runtime error:", text)
        ):
            raise RuntimeError("LZ4 sanitizer suite reported a defect")
        compilers[compiler] = {
            "compile_actions": actions,
            "production_sources": len(sources),
            "compile_database_sha256": sha256(database),
            "upstream_essentials_log_sha256": sha256(log),
            "passed": True,
        }

    differential_path = oracle / "differential.json"
    differential = json.loads(differential_path.read_text())
    if differential.get("cases") != 27 or differential.get("passed") != 27:
        raise RuntimeError("LZ4 differential suite is incomplete")

    valgrind = {}
    expected_heaps = {
        "compress": "total heap usage: 9 allocs, 9 frees, 8,410,567 bytes allocated",
        "decompress": "total heap usage: 29 allocs, 29 frees, 29,633,156 bytes allocated",
    }
    for operation, heap in expected_heaps.items():
        path = oracle / f"valgrind-{operation}.log"
        text = path.read_text(errors="replace")
        if (
            "ERROR SUMMARY: 0 errors" not in text
            or "All heap blocks were freed -- no leaks are possible" not in text
            or heap not in text
        ):
            raise RuntimeError(f"LZ4 {operation} Valgrind gate changed")
        valgrind[operation] = {
            "errors": 0, "all_allocations_freed": True,
            "heap_summary": heap, "log_sha256": sha256(path),
        }

    binaries = {}
    for compiler in ("gcc", "clang"):
        binary = oracle / compiler / "lz4"
        with tempfile.TemporaryDirectory(prefix="rustbox-lz4-strip-") as temporary:
            stripped = Path(temporary) / "lz4"
            shutil.copy2(binary, stripped)
            subprocess.run(["strip", "--strip-all", str(stripped)], check=True)
            stripped_bytes = stripped.stat().st_size
            stripped_sha256 = sha256(stripped)
        dependencies = needed(binary)
        if dependencies != ["libc.so.6"]:
            raise RuntimeError(f"LZ4 {compiler} has unexpected dependencies: {dependencies}")
        binaries[compiler] = {
            "bytes": binary.stat().st_size,
            "sha256": sha256(binary),
            "stripped_bytes": stripped_bytes,
            "stripped_sha256": stripped_sha256,
            "dynamic_needed": dependencies,
        }

    line_counts = {
        name: len((source / name).read_text(errors="replace").splitlines())
        for name in expected_sources
    }
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-21",
        "release": "1.11.1",
        "status": "complete canonical checksum-authenticated oracle; normalization pending",
        "source": {
            "kind": state["source_kind"],
            "archive": state["archive"],
            "archive_sha256": state["sha256"],
            "checksum_sha256": state["checksum_sha256"],
            "checksum_verified": state["checksum_verified"],
            "signature_verified": False,
            "authentication_limit": state["authentication"],
            "tag": state["tag"],
            "commit": state["commit"],
            "archive_members": archive_members,
            "state_sha256": sha256(state_path),
        },
        "inventory": {
            "public_names": ["lz4", "lz4c", "lz4cat", "unlz4"],
            "physical_executables": 1,
            "production_sources": expected_sources,
            "production_source_count": len(expected_sources),
            "source_lines": line_counts,
            "total_source_lines": sum(line_counts.values()),
            "multithreaded": True,
        },
        "compilers": compilers,
        "behavior": {
            "upstream_essentials": {"gcc": "pass", "clang": "pass", "sanitizer": "pass"},
            "differential": differential,
            "differential_sha256": sha256(differential_path),
            "valgrind": valgrind,
        },
        "binaries": binaries,
        "configuration": {"external_liblz4": False, "systemd": False, "selinux": False},
        "next_gate": "five-analyzer audit and deterministic normalization of the exact 12-source closure",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "differential": differential["passed"],
        "production_sources": len(expected_sources),
        "source_lines": sum(line_counts.values()),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
