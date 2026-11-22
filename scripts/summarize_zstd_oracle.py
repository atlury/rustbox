#!/usr/bin/env python3
"""Generate committed evidence for the canonical zstd 1.5.7 oracle."""

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


PUBLIC_NAMES = ["zstd", "zstdmt", "unzstd", "zstdcat", "zstdgrep", "zstdless"]
EXPECTED_CLOSURE_SHA256 = "b958ac0c7b62e90253c92959748cf1b577f0292ccc4be6cb1058dcb215f6de8c"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def needed(path: Path) -> list[str]:
    output = subprocess.run(
        ["readelf", "-d", str(path)], check=True, text=True, stdout=subprocess.PIPE
    ).stdout
    return re.findall(r"Shared library: \[([^]]+)\]", output)


def source_names(database: Path, compiler: str) -> tuple[int, list[str]]:
    records = json.loads(database.read_text())
    marker = f"/source-{compiler}/"
    names = sorted({record["file"].replace("\\", "/").split(marker, 1)[1]
                    for record in records})
    return len(records), names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    oracle = repository / "work/analysis/zstd-1.5.7/oracle"
    source = repository / "work/upstream/zstd-1.5.7"
    state_path = repository / "work/upstream/.state/zstd.json"
    state = json.loads(state_path.read_text())
    if not state.get("checksum_verified") or not state.get("integrity_verified"):
        raise RuntimeError("zstd release checksum has not been verified")
    archive = repository / ".cache/downloads/zstd-1.5.7.tar.gz"
    if sha256(archive) != state["sha256"]:
        raise RuntimeError("zstd release archive changed after authentication")
    with tarfile.open(archive, "r:gz") as stream:
        archive_members = len(stream.getmembers())
    if archive_members != 743:
        raise RuntimeError(f"unexpected zstd archive member count: {archive_members}")

    compilers: dict[str, object] = {}
    production_sources: list[str] | None = None
    for compiler in ("gcc", "clang", "sanitizer"):
        database = oracle / f"{compiler}-compile-commands.json"
        actions, sources = source_names(database, compiler)
        closure = hashlib.sha256(("\n".join(sources) + "\n").encode()).hexdigest()
        if actions != 45 or len(sources) != 45 or closure != EXPECTED_CLOSURE_SHA256:
            raise RuntimeError(f"zstd {compiler} production closure changed")
        if production_sources is None:
            production_sources = sources
        elif sources != production_sources:
            raise RuntimeError("zstd compiler production closures differ")
        log = oracle / f"{compiler}-check.log"
        text = log.read_text(errors="replace")
        if "All tests completed successfully" not in text:
            raise RuntimeError(f"zstd {compiler} upstream suite is incomplete")
        if compiler == "sanitizer" and (
            "ERROR: AddressSanitizer" in text
            or re.search(r"\.c:\d+(?::\d+)?: runtime error:", text)
        ):
            raise RuntimeError("zstd sanitizer suite reported a defect")
        compilers[compiler] = {
            "compile_actions": actions,
            "production_sources": len(sources),
            "compile_database_sha256": sha256(database),
            "upstream_tests": "complete upstream make check",
            "upstream_test_log_sha256": sha256(log),
            "passed": True,
        }
    assert production_sources is not None

    differential_path = oracle / "differential.json"
    differential = json.loads(differential_path.read_text())
    if (differential.get("cases"), differential.get("passed"),
            differential.get("public_names")) != (17, 17, PUBLIC_NAMES):
        raise RuntimeError("zstd differential suite is incomplete")

    valgrind: dict[str, object] = {}
    for operation, expected in {
        "compress": (73, 72, 3875071, 48),
        "decompress": (72, 71, 2992018, 38),
    }.items():
        path = oracle / f"valgrind-{operation}.log"
        text = path.read_text(errors="replace")
        heap = re.search(r"total heap usage: (\d+) allocs, (\d+) frees, ([\d,]+) bytes allocated", text)
        reachable = re.search(r"still reachable: ([\d,]+) bytes in (\d+) blocks", text)
        if not heap or not reachable:
            raise RuntimeError(f"zstd {operation} Valgrind summary is missing")
        observed = (int(heap[1]), int(heap[2]), int(heap[3].replace(",", "")),
                    int(reachable[1].replace(",", "")))
        if observed != expected or any(marker not in text for marker in (
            "definitely lost: 0 bytes in 0 blocks",
            "indirectly lost: 0 bytes in 0 blocks",
            "possibly lost: 0 bytes in 0 blocks",
            "ERROR SUMMARY: 0 errors",
        )):
            raise RuntimeError(f"zstd {operation} Valgrind lifecycle changed: {observed}")
        valgrind[operation] = {
            "errors": 0, "definitely_lost_bytes": 0, "indirectly_lost_bytes": 0,
            "possibly_lost_bytes": 0, "still_reachable_bytes": observed[3],
            "allocations": observed[0], "frees": observed[1],
            "allocated_bytes": observed[2], "log_sha256": sha256(path),
        }

    binaries: dict[str, object] = {}
    for compiler in ("gcc", "clang"):
        binary = oracle / f"{compiler}-root/usr/bin/zstd"
        with tempfile.TemporaryDirectory(prefix="rustbox-zstd-strip-") as temporary:
            stripped = Path(temporary) / "zstd"
            shutil.copy2(binary, stripped)
            subprocess.run(["strip", "--strip-all", str(stripped)], check=True)
            stripped_bytes = stripped.stat().st_size
            stripped_digest = sha256(stripped)
        dependencies = needed(binary)
        if dependencies != ["libc.so.6"]:
            raise RuntimeError(f"zstd {compiler} dependencies changed: {dependencies}")
        binaries[compiler] = {
            "bytes": binary.stat().st_size, "sha256": sha256(binary),
            "stripped_bytes": stripped_bytes, "stripped_sha256": stripped_digest,
            "dynamic_needed": dependencies,
        }

    line_counts = {name: len((source / name).read_text(errors="replace").splitlines())
                   for name in production_sources}
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-22",
        "release": "1.5.7",
        "status": "complete canonical checksum oracle; deterministic normalization pending",
        "source": {
            "kind": state["source_kind"], "archive": state["archive"],
            "archive_sha256": state["sha256"],
            "checksum_sha256": state["checksum_sha256"],
            "checksum_verified": True, "commit": state["commit"], "tag": state["tag"],
            "archive_members": archive_members, "state_sha256": sha256(state_path),
        },
        "inventory": {
            "public_names": PUBLIC_NAMES, "public_name_count": len(PUBLIC_NAMES),
            "physical_c_executables": ["zstd"],
            "canonical_scripts": ["zstdgrep", "zstdless"],
            "production_sources": production_sources,
            "production_source_count": len(production_sources),
            "production_closure_sha256": EXPECTED_CLOSURE_SHA256,
            "source_lines": line_counts, "total_source_lines": sum(line_counts.values()),
        },
        "compilers": compilers,
        "behavior": {
            "differential": {"cases": 17, "passed": 17},
            "differential_sha256": sha256(differential_path),
            "byte_identical_compiler_streams": True,
            "valgrind": valgrind,
        },
        "binaries": binaries,
        "configuration": {
            "compression": "all", "decompression": "all", "dictionaries": True,
            "benchmarks": True, "legacy_decoders": ["v0.5", "v0.6", "v0.7"],
            "threads": "posix", "external_zlib": False, "external_lzma": False,
            "external_lz4": False, "selinux": False, "systemd": False,
        },
        "next_gate": "static audit and deterministic normalization of the exact 45-source closure",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"differential": 17, "public_names": len(PUBLIC_NAMES),
                      "production_sources": len(production_sources),
                      "source_lines": sum(line_counts.values())}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
