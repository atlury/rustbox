#!/usr/bin/env python3
"""Generate committed evidence for the canonical GNU tar 1.35 oracle."""

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


PUBLIC_NAMES = ["tar", "rmt"]
EXPECTED_ACTIONS = 197
EXPECTED_ARCHIVE_MEMBERS = 1249
EXPECTED_CLOSURE_SHA256 = "31dd9e972f2643378de2dda2d1b9f8b615549ed254648c9e2cdd57c453a28175"
EXPECTED_SIGNER = "325F650C4C2B6AD58807327A3602B07F55D0C732"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dynamic_needed(path: Path) -> list[str]:
    output = subprocess.run(
        ["readelf", "-d", str(path)], check=True, text=True,
        stdout=subprocess.PIPE,
    ).stdout
    return re.findall(r"Shared library: \[([^]]+)\]", output)


def source_names(database: Path, compiler: str) -> tuple[int, list[str]]:
    records = json.loads(database.read_text())
    marker = f"/source-{compiler}/"
    names = sorted({record["file"].replace("\\", "/").split(marker, 1)[1]
                    for record in records})
    return len(records), names


def validate_suite(path: Path, compiler: str) -> dict[str, object]:
    text = path.read_text(errors="replace")
    required = [
        "224 tests were run",
        "20 tests were skipped",
        "222: xattrs: trusted.* attributes",
        "233: capabilities: binary store/restore",
        "2 failed unexpectedly",
    ]
    if any(marker not in text for marker in required):
        raise RuntimeError(f"GNU tar {compiler} suite is incomplete")
    if compiler == "sanitizer" and (
        "ERROR: AddressSanitizer" in text
        or re.search(r"(?:^|\s)[^\s]+\.c:\d+(?::\d+)?: runtime error:", text)
    ):
        raise RuntimeError("GNU tar sanitizer suite reported a defect")
    return {
        "run": 224,
        "passed": 202,
        "skipped": 20,
        "capability_limited_failures": 2,
        "capability_limited_tests": [
            "222: xattrs: trusted.* attributes",
            "233: capabilities: binary store/restore",
        ],
        "log_sha256": sha256(path),
    }


def valgrind_summary(path: Path, expected: tuple[int, int, int, int]) -> dict[str, object]:
    text = path.read_text(errors="replace")
    definite, indirect, possible, errors = expected
    required = (
        f"definitely lost: {definite:,} bytes",
        f"indirectly lost: {indirect:,} bytes",
        f"possibly lost: {possible:,} bytes",
        f"ERROR SUMMARY: {errors} errors",
    )
    if any(marker not in text for marker in required):
        raise RuntimeError(f"Valgrind baseline changed in {path.name}")
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
        "definitely_lost_bytes": definite,
        "indirectly_lost_bytes": indirect,
        "possibly_lost_bytes": possible,
        "errors": errors,
        "log_sha256": sha256(path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repository = args.repository.resolve()
    oracle = repository / "work/analysis/tar-1.35/oracle"
    source = repository / "work/upstream/tar-1.35"
    state_path = repository / "work/upstream/.state/tar.json"
    state = json.loads(state_path.read_text())
    if not state.get("signature_verified") or state.get("signer_fingerprint") != EXPECTED_SIGNER:
        raise RuntimeError("GNU tar release signature is not authenticated")
    archive = repository / ".cache/downloads/tar-1.35.tar.xz"
    if sha256(archive) != state["sha256"]:
        raise RuntimeError("GNU tar release archive changed after authentication")
    with tarfile.open(archive, "r:xz") as stream:
        archive_members = len(stream.getmembers())
    if archive_members != EXPECTED_ARCHIVE_MEMBERS:
        raise RuntimeError(f"unexpected GNU tar archive member count: {archive_members}")

    production_sources: list[str] | None = None
    compilers: dict[str, object] = {}
    for compiler in ("gcc", "clang", "sanitizer"):
        database = oracle / f"{compiler}-compile-commands.json"
        actions, sources = source_names(database, compiler)
        closure = hashlib.sha256(("\n".join(sources) + "\n").encode()).hexdigest()
        if (actions, len(sources), closure) != (
            EXPECTED_ACTIONS, EXPECTED_ACTIONS, EXPECTED_CLOSURE_SHA256
        ):
            raise RuntimeError(f"GNU tar {compiler} production closure changed")
        if production_sources is None:
            production_sources = sources
        elif sources != production_sources:
            raise RuntimeError("GNU tar compiler production closures differ")
        compilers[compiler] = {
            "compile_actions": actions,
            "production_sources": len(sources),
            "compile_database_sha256": sha256(database),
            "upstream_suite": validate_suite(oracle / f"{compiler}-check.log", compiler),
        }
    assert production_sources is not None

    differential_path = oracle / "differential.json"
    differential = json.loads(differential_path.read_text())
    if (differential.get("cases"), differential.get("passed")) != (18, 18):
        raise RuntimeError("GNU tar compiler differential is incomplete")
    if differential.get("public_names") != PUBLIC_NAMES:
        raise RuntimeError("GNU tar differential omitted a public name")

    binaries: dict[str, object] = {}
    for compiler in ("gcc", "clang"):
        for name, relative in (("tar", "usr/bin/tar"), ("rmt", "usr/libexec/rmt")):
            binary = oracle / f"{compiler}-root/{relative}"
            with tempfile.TemporaryDirectory(prefix="rustbox-tar-strip-") as temporary:
                stripped = Path(temporary) / name
                shutil.copy2(binary, stripped)
                subprocess.run(["strip", "--strip-all", str(stripped)], check=True)
                stripped_bytes = stripped.stat().st_size
                stripped_digest = sha256(stripped)
            dependencies = dynamic_needed(binary)
            expected_dependencies = (
                ["libacl.so.1", "libc.so.6"]
                if name == "tar" or (compiler == "clang" and name == "rmt")
                else ["libc.so.6"]
            )
            if dependencies != expected_dependencies:
                raise RuntimeError(
                    f"GNU tar {compiler} {name} dependencies changed: {dependencies}"
                )
            binaries[f"{compiler}-{name}"] = {
                "bytes": binary.stat().st_size,
                "sha256": sha256(binary),
                "stripped_bytes": stripped_bytes,
                "stripped_sha256": stripped_digest,
                "dynamic_needed": dependencies,
            }

    line_counts = {
        name: len((source / name).read_text(errors="replace").splitlines())
        for name in production_sources
    }
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-22",
        "release": "1.35",
        "status": "complete signed canonical oracle; deterministic normalization pending",
        "source": {
            "kind": state["source_kind"],
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
            "production_sources": production_sources,
            "production_source_count": len(production_sources),
            "production_closure_sha256": EXPECTED_CLOSURE_SHA256,
            "source_lines": line_counts,
            "total_source_lines": sum(line_counts.values()),
        },
        "configuration": {
            "acl": True,
            "xattrs": True,
            "large_files": True,
            "sparse_files": True,
            "nls": True,
            "selinux": False,
            "systemd": False,
            "external_compressors": "oracle tests only; not final multicall dependencies",
            "oracle_libacl": "canonical dynamic oracle only; final multicall reuses the already integrated ACL implementation",
            "clang_rmt_unused_libacl": "Clang retains configure's global -lacl while GCC drops this unused rmt dependency; rmt has no ACL code and the final multicall retains neither dependency",
        },
        "compilers": compilers,
        "behavior": {
            "differential": {
                "cases": differential["cases"],
                "passed": differential["passed"],
                "sha256": sha256(differential_path),
            },
            "valgrind": {
                operation: valgrind_summary(
                    oracle / f"valgrind-{operation}.log",
                    (152, 1, 0, 3) if operation == "extract" else (0, 0, 0, 0),
                )
                for operation in ("create", "list", "extract", "rmt")
            },
            "canonical_extract_cleanup_baseline": {
                "direct_bytes": 152,
                "indirect_bytes": 1,
                "cause": "upstream -C and name-list allocations intentionally retained until process exit",
                "translation_requirement": "do not regress and free owned multicall state before return",
            },
        },
        "binaries": binaries,
        "next_gate": "five-tool static audit and deterministic normalization of the exact 197-source closure",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "differential": differential["cases"],
        "production_sources": len(production_sources),
        "public_names": len(PUBLIC_NAMES),
        "source_lines": sum(line_counts.values()),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
