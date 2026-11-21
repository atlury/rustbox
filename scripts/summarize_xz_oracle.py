#!/usr/bin/env python3
"""Generate committed evidence for the canonical XZ Utils 5.8.4 oracle."""

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


PUBLIC_NAMES = [
    "xz", "unxz", "xzcat", "lzma", "unlzma", "lzcat", "xzdec",
    "lzmadec", "lzmainfo", "xzdiff", "xzcmp", "xzegrep", "xzfgrep",
    "xzgrep", "xzless", "xzmore", "lzdiff", "lzcmp", "lzgrep",
    "lzegrep", "lzfgrep", "lzmore", "lzless",
]
EXPECTED_CLOSURE_SHA256 = "1d9270fb42e95e59fd9bbc00a583d21d5cf84896cac89b4a5ab429d38cb7f7a2"


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
    oracle = repository / "work/analysis/xz-5.8.4/oracle"
    source = repository / "work/upstream/xz-5.8.4"
    state_path = repository / "work/upstream/.state/xz.json"
    state = json.loads(state_path.read_text())
    if not state.get("signature_verified"):
        raise RuntimeError("XZ release signature has not been verified")
    archive = repository / ".cache/downloads/xz-5.8.4.tar.xz"
    if sha256(archive) != state["sha256"]:
        raise RuntimeError("XZ release archive changed after authentication")
    with tarfile.open(archive, "r:xz") as stream:
        archive_members = len(stream.getmembers())
    if archive_members != 704:
        raise RuntimeError(f"unexpected XZ archive member count: {archive_members}")

    compilers: dict[str, object] = {}
    production_sources: list[str] | None = None
    for compiler in ("gcc", "clang", "sanitizer"):
        database = oracle / f"{compiler}-compile-commands.json"
        actions, sources = source_names(database, compiler)
        closure = hashlib.sha256(("\n".join(sources) + "\n").encode()).hexdigest()
        if actions != 113 or len(sources) != 101 or closure != EXPECTED_CLOSURE_SHA256:
            raise RuntimeError(f"XZ {compiler} production closure changed")
        if production_sources is None:
            production_sources = sources
        elif sources != production_sources:
            raise RuntimeError("XZ compiler production closures differ")
        log = oracle / f"{compiler}-check.log"
        text = log.read_text(errors="replace")
        for marker in ("# TOTAL: 22", "# PASS:  22", "# SKIP:  0",
                       "# FAIL:  0", "# ERROR: 0"):
            if marker not in text:
                raise RuntimeError(f"XZ {compiler} upstream suite is incomplete")
        if compiler == "sanitizer" and (
            "ERROR: AddressSanitizer" in text
            or re.search(r"\.c:\d+(?::\d+)?: runtime error:", text)
        ):
            raise RuntimeError("XZ sanitizer suite reported a defect")
        compilers[compiler] = {
            "compile_actions": actions,
            "production_sources": len(sources),
            "compile_database_sha256": sha256(database),
            "upstream_tests": {"total": 22, "passed": 22, "skipped": 0},
            "upstream_test_log_sha256": sha256(log),
            "landlock": compiler != "sanitizer",
            "passed": True,
        }
    assert production_sources is not None

    differential_path = oracle / "differential.json"
    differential = json.loads(differential_path.read_text())
    if (differential.get("cases"), differential.get("passed"),
            differential.get("public_names")) != (70, 70, PUBLIC_NAMES):
        raise RuntimeError("XZ differential suite is incomplete")

    expected_valgrind = {
        "compress": (15, 1, 97598557, 97598539),
        "decompress": (10, 2, 8424607, 8424480),
    }
    valgrind: dict[str, object] = {}
    for operation, expected in expected_valgrind.items():
        path = oracle / f"valgrind-{operation}.log"
        text = path.read_text(errors="replace")
        heap = re.search(r"total heap usage: (\d+) allocs, (\d+) frees, ([\d,]+) bytes allocated", text)
        reachable = re.search(r"still reachable: ([\d,]+) bytes in (\d+) blocks", text)
        if not heap or not reachable:
            raise RuntimeError(f"XZ {operation} Valgrind summary is missing")
        observed = (int(heap[1]), int(heap[2]), int(heap[3].replace(",", "")),
                    int(reachable[1].replace(",", "")))
        if observed != expected or any(marker not in text for marker in (
            "definitely lost: 0 bytes in 0 blocks",
            "indirectly lost: 0 bytes in 0 blocks",
            "possibly lost: 0 bytes in 0 blocks",
            "ERROR SUMMARY: 0 errors",
        )):
            raise RuntimeError(f"XZ {operation} Valgrind lifecycle changed: {observed}")
        valgrind[operation] = {
            "errors": 0, "definitely_lost_bytes": 0, "indirectly_lost_bytes": 0,
            "possibly_lost_bytes": 0, "still_reachable_bytes": observed[3],
            "allocations": observed[0], "frees": observed[1],
            "allocated_bytes": observed[2], "log_sha256": sha256(path),
        }

    binaries: dict[str, object] = {}
    for compiler in ("gcc", "clang"):
        binaries[compiler] = {}
        for name in ("xz", "xzdec", "lzmadec", "lzmainfo"):
            binary = oracle / f"{compiler}-root/usr/bin" / name
            with tempfile.TemporaryDirectory(prefix="rustbox-xz-strip-") as temporary:
                stripped = Path(temporary) / name
                shutil.copy2(binary, stripped)
                subprocess.run(["strip", "--strip-all", str(stripped)], check=True)
                stripped_bytes = stripped.stat().st_size
                stripped_digest = sha256(stripped)
            dependencies = needed(binary)
            if dependencies != ["libc.so.6"]:
                raise RuntimeError(f"XZ {compiler} {name} dependencies changed: {dependencies}")
            binaries[compiler][name] = {
                "bytes": binary.stat().st_size, "sha256": sha256(binary),
                "stripped_bytes": stripped_bytes, "stripped_sha256": stripped_digest,
                "dynamic_needed": dependencies,
            }

    line_counts = {name: len((source / name).read_text(errors="replace").splitlines())
                   for name in production_sources}
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-22",
        "release": "5.8.4",
        "status": "complete canonical signed oracle; deterministic normalization pending",
        "source": {
            "kind": state["source_kind"], "archive": state["archive"],
            "archive_sha256": state["sha256"],
            "signature_sha256": state["signature_sha256"],
            "signature_verified": True,
            "signer_fingerprint": state["signer_fingerprint"],
            "archive_members": archive_members, "state_sha256": sha256(state_path),
        },
        "inventory": {
            "public_names": PUBLIC_NAMES, "public_name_count": len(PUBLIC_NAMES),
            "physical_c_executables": ["xz", "xzdec", "lzmadec", "lzmainfo"],
            "canonical_scripts": ["xzdiff", "xzgrep", "xzless", "xzmore"],
            "production_sources": production_sources,
            "production_source_count": len(production_sources),
            "production_closure_sha256": EXPECTED_CLOSURE_SHA256,
            "source_lines": line_counts, "total_source_lines": sum(line_counts.values()),
        },
        "compilers": compilers,
        "behavior": {
            "differential": {"cases": 70, "passed": 70},
            "differential_sha256": sha256(differential_path),
            "byte_identical_compiler_streams": ["xz", "lzma"],
            "valgrind": valgrind,
        },
        "binaries": binaries,
        "configuration": {
            "encoders": "all", "decoders": "all", "match_finders": "all",
            "checks": ["crc32", "crc64", "sha256"], "threads": "posix",
            "microlzma": True, "lzip_decoder": True, "external_liblzma": False,
            "nls": False, "selinux": False, "systemd": False,
        },
        "next_gate": "five-analyzer audit and deterministic normalization of the exact 101-source closure",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"differential": 70, "public_names": len(PUBLIC_NAMES),
                      "production_sources": len(production_sources),
                      "source_lines": sum(line_counts.values())}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
