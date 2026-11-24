#!/usr/bin/env python3
"""Publish reproducible signed E2fsprogs 1.47.4 oracle evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


PROGRAM_PATHS = (
    "sbin/badblocks", "sbin/debugfs", "sbin/dumpe2fs", "sbin/e2fsck",
    "sbin/e2image", "sbin/e2label", "sbin/e2mmpstatus", "sbin/e2scrub",
    "sbin/e2scrub_all", "sbin/e2undo", "sbin/fsck", "sbin/fsck.ext2",
    "sbin/fsck.ext3", "sbin/fsck.ext4", "sbin/logsave", "sbin/mke2fs",
    "sbin/mkfs.ext2", "sbin/mkfs.ext3", "sbin/mkfs.ext4", "sbin/resize2fs",
    "sbin/tune2fs", "usr/bin/chattr", "usr/bin/compile_et", "usr/bin/fuse2fs",
    "usr/bin/lsattr", "usr/bin/mk_cmds", "usr/lib/e2initrd_helper",
    "usr/sbin/e2freefrag", "usr/sbin/e4crypt", "usr/sbin/e4defrag",
    "usr/sbin/filefrag", "usr/sbin/mklost+found",
)
ALIASES = {
    "sbin/dumpe2fs": ["sbin/e2mmpstatus"],
    "sbin/e2fsck": ["sbin/fsck.ext2", "sbin/fsck.ext3", "sbin/fsck.ext4"],
    "sbin/mke2fs": ["sbin/mkfs.ext2", "sbin/mkfs.ext3", "sbin/mkfs.ext4"],
    "sbin/tune2fs": ["sbin/e2label"],
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_closure(path: Path, compiler: str) -> tuple[list[str], int]:
    records = json.loads(path.read_text())
    source_root = Path("/work/work/upstream/e2fsprogs-1.47.4")
    build_root = Path(f"/rustbox-e2fsprogs/oracle-{compiler}")
    sources = set()
    for record in records:
        source = (Path(record["directory"]) / record["file"]).resolve()
        if source.is_relative_to(source_root):
            relative = "source/" + str(source.relative_to(source_root))
        elif source.is_relative_to(build_root):
            relative = "generated/" + str(source.relative_to(build_root))
        else:
            raise RuntimeError(f"E2fsprogs compile action escaped its source/build roots: {source}")
        sources.add(relative)
    return sorted(sources), len(records)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.repository.resolve()
    oracle = root / "work/analysis/e2fsprogs-1.47.4/oracle"
    analyzers = root / "work/analysis/e2fsprogs-1.47.4/analyzers"
    state = json.loads((root / "work/upstream/.state/e2fsprogs.json").read_text())
    expected_authentication = {
        "version": "1.47.4",
        "sha256": "fd5bf388cbdbe006a3d3b318d983b2948382440acc85a87f1e7d108653e8db0b",
        "signature_sha256": "ff826cf86828bf3ed8a7fcbe3e5c0c171f8ebfc5f46c43b27adc1ffc2c6a7b9c",
        "key_sha256": "aefee846527b1ac909a61d1251f0ba67ca66fd5a3be66d97169f5dc18d1720f9",
        "signer_fingerprint": "2B69B954DBFE0879288137C9F2F95956950D81A3",
        "signature_mode": "uncompressed-tar",
        "signature_verified": True,
        "archive_members_verified": 2794,
    }
    for key, value in expected_authentication.items():
        if state.get(key) != value:
            raise RuntimeError(f"E2fsprogs source authentication changed: {key}")

    compile_databases = {}
    closures = []
    for compiler, actions in (("gcc", 240), ("clang-18", 241)):
        path = oracle / f"{compiler}-compile-commands.json"
        sources, actual_actions = source_closure(path, compiler)
        if actual_actions != actions or len(sources) != 232:
            raise RuntimeError(f"E2fsprogs {compiler} compile closure changed")
        closures.append(sources)
        compile_databases[compiler] = {
            "compile_actions": actual_actions,
            "sources": len(sources),
            "sha256": sha256(path),
        }
    if closures[0] != closures[1]:
        raise RuntimeError("E2fsprogs GCC and Clang source closures differ")

    installed = {}
    dependency_union = set()
    for compiler in ("gcc", "clang-18"):
        inventory_path = oracle / f"{compiler}-installed-executables.txt"
        paths = tuple(inventory_path.read_text().splitlines())
        metadata_path = oracle / f"{compiler}-installed-metadata.json"
        metadata = json.loads(metadata_path.read_text())
        if paths != PROGRAM_PATHS or metadata.get("installed_names") != 32:
            raise RuntimeError(f"E2fsprogs {compiler} installed inventory changed")
        if metadata.get("engines") != 24 or metadata.get("hardlink_aliases") != ALIASES:
            raise RuntimeError(f"E2fsprogs {compiler} alias topology changed")
        kinds = [record["kind"] for record in metadata["records"]]
        if kinds.count("elf") != 28 or kinds.count("script") != 4:
            raise RuntimeError(f"E2fsprogs {compiler} frontend kinds changed")
        dependencies = sorted({
            dependency for record in metadata["records"]
            for dependency in record["dynamic_dependencies"]
        })
        if dependencies != ["libblkid.so.1", "libc.so.6", "libfuse3.so.3", "libuuid.so.1"]:
            raise RuntimeError(f"E2fsprogs {compiler} dependencies changed: {dependencies}")
        dependency_union.update(dependencies)
        installed[compiler] = {
            "inventory_sha256": sha256(inventory_path),
            "metadata_sha256": sha256(metadata_path),
            "installed_names": 32,
            "engines": 24,
            "elf_names": 28,
            "script_names": 4,
            "dynamic_dependencies": dependencies,
        }

    differential_path = oracle / "differential.json"
    differential = json.loads(differential_path.read_text())
    if (
        differential.get("programs") != 32
        or differential.get("cases") != 96
        or differential.get("passed") != 96
        or not all(record.get("passed") for record in differential.get("records", []))
    ):
        raise RuntimeError("E2fsprogs compiler differential changed")

    tests = {}
    for compiler in ("gcc", "clang-18"):
        path = oracle / f"{compiler}-test.log"
        text = path.read_text(errors="replace")
        passed = sum(line.endswith(": ok") for line in text.splitlines())
        skipped = sum(": skipped" in line for line in text.splitlines())
        failed = sum(line.endswith(": failed") for line in text.splitlines())
        if (
            (oracle / f"{compiler}-test.status").read_text().strip() != "2"
            or (passed, skipped, failed) != (396, 10, 1)
            or "Tests failed: m_assume_storage_prezeroed" not in text
        ):
            raise RuntimeError(f"E2fsprogs {compiler} upstream suite changed")
        tests[compiler] = {
            "passed": passed,
            "skipped": skipped,
            "environmental_failures": failed,
            "sha256": sha256(path),
        }

    resource_profiles = {}
    native = scripts = 0
    for relative in PROGRAM_PATHS:
        name = relative.replace("/", "_")
        path = oracle / f"valgrind-{name}.log"
        text = path.read_text(errors="replace")
        if "ERROR SUMMARY: 0 errors" in text:
            kind = "valgrind"
            native += 1
        elif "script syntax valid" in text:
            kind = "script-syntax"
            scripts += 1
        else:
            raise RuntimeError(f"E2fsprogs resource profile changed: {relative}")
        resource_profiles[relative] = {"kind": kind, "sha256": sha256(path)}
    if (native, scripts) != (28, 4):
        raise RuntimeError("E2fsprogs resource inventory changed")

    analyzer_status = {
        name: (analyzers / f"{name}.status").read_text().strip()
        for name in ("cppcheck", "gcc-analyzer", "clang-analyzer-tidy", "flawfinder", "sparse")
    }
    gcc_summary = json.loads((analyzers / "gcc-analyzer-summary.json").read_text())
    expected_analyzer_status = {
        "cppcheck": "0",
        "gcc-analyzer": "0",
        "clang-analyzer-tidy": "0",
        "flawfinder": "0",
        "sparse": "123",
    }
    if (
        analyzer_status != expected_analyzer_status
        or gcc_summary.get("compile_actions") != 232
        or gcc_summary.get("passed") != 232
        or gcc_summary.get("failed") != 0
        or gcc_summary.get("timed_out") != 0
    ):
        raise RuntimeError(f"E2fsprogs core static-analysis gate changed: {analyzer_status}, {gcc_summary}")
    flawfinder_text = (analyzers / "flawfinder.log").read_text(errors="replace")
    flawfinder_hits = re.findall(r"^Hits = ([0-9]+)$", flawfinder_text, re.MULTILINE)
    if flawfinder_hits != ["1173"]:
        raise RuntimeError(f"E2fsprogs Flawfinder baseline changed: {flawfinder_hits}")
    analyzer_evidence = {
        "source_closure": 232,
        "statuses": analyzer_status,
        "gcc_analyzer": gcc_summary,
        "flawfinder_level_1_or_higher_hits": 1173,
        "sparse_diagnostic_lines": len((analyzers / "sparse.log").read_text(errors="replace").splitlines()),
        "logs": {
            name: sha256(analyzers / f"{name}.log")
            for name in ("cppcheck", "gcc-analyzer", "clang-analyzer-tidy", "flawfinder", "sparse")
        },
    }

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-24",
        "release": "1.47.4",
        "status": "complete signed canonical E2fsprogs oracle; deterministic normalization pending",
        "source_authentication": expected_authentication,
        "scope": {
            "installed_names": 32,
            "engines": 24,
            "elf_names": 28,
            "script_names": 4,
            "program_paths": list(PROGRAM_PATHS),
            "hardlink_aliases": ALIASES,
            "installed_build_helpers": ["compile_et", "mk_cmds"],
            "installed_runtime_helpers": ["e2initrd_helper"],
            "absent_under_canonical_util_linux_libraries": ["findfs", "blkid", "uuidd", "uuidgen"],
            "excluded_infrastructure": ["systemd units", "udev rules", "cron installation", "SELinux libraries"],
        },
        "compile_databases": compile_databases,
        "installed": installed,
        "differential": {
            "cases": 96,
            "passed": 96,
            "physical_argv0_normalized": True,
            "isolated_filesystem_effects_compared": True,
            "sha256": sha256(differential_path),
        },
        "upstream_tests": tests,
        "environmental_failure": {
            "test": "m_assume_storage_prezeroed",
            "expected_allocated_512_byte_blocks": 224,
            "docker_overlay_loop_allocated_512_byte_blocks": 232,
            "identical_across_compilers": True,
        },
        "resource_profiles": {
            "native_valgrind_clean": native,
            "scripts_syntax_clean": scripts,
            "records": resource_profiles,
        },
        "static_analysis": analyzer_evidence,
        "integration_policy": {
            "collisions": {"fsck": "util-linux"},
            "aliases": {"e2fsprogs-fsck": "E2fsprogs fsck"},
            "new_unaliased_names": 31,
            "final_runtime_external_libraries_permitted": False,
        },
        "next_gate": "deterministic multicall entrypoint normalization for 24 engines",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "installed_names": 32,
        "engines": 24,
        "differential_passed": 96,
        "upstream_passed_per_compiler": 396,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
