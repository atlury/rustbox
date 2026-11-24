#!/usr/bin/env python3
"""Validate and publish deterministic E2fsprogs normalization evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_counts(path: Path) -> tuple[int, int, int]:
    lines = path.read_text(errors="replace").splitlines()
    return (
        sum(line.endswith(": ok") for line in lines),
        sum(": skipped" in line for line in lines),
        sum(line.endswith(": failed") for line in lines),
    )


def source_closure(records: list[dict[str, object]], compiler: str) -> list[str]:
    source_root = Path("/work/work/normalized/e2fsprogs-1.47.4")
    build_root = Path(f"/rustbox-e2fsprogs/normalized-{compiler}")
    sources = set()
    for record in records:
        source = (Path(str(record["directory"])) / str(record["file"])).resolve()
        if source.is_relative_to(source_root):
            relative = "source/" + str(source.relative_to(source_root))
        elif source.is_relative_to(build_root):
            relative = "generated/" + str(source.relative_to(build_root))
        else:
            raise RuntimeError(f"E2fsprogs compile action escaped normalized roots: {source}")
        sources.add(relative)
    return sorted(sources)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.repository.resolve()
    evidence = root / "work/analysis/e2fsprogs-1.47.4/normalization"
    manifest = json.loads((evidence / "manifest.json").read_text())
    if (
        manifest.get("native_engines") != 20
        or manifest.get("native_names") != 28
        or manifest.get("script_engines") != ["e2scrub", "e2scrub_all", "compile_et", "mk_cmds"]
        or len(manifest.get("changed_sources", [])) != 20
    ):
        raise RuntimeError("E2fsprogs normalization manifest changed")

    builds = {}
    closures = []
    for compiler, actions in (("gcc", 240), ("clang-18", 241)):
        inventory = tuple((evidence / f"{compiler}-installed-executables.txt").read_text().splitlines())
        if inventory != PROGRAM_PATHS:
            raise RuntimeError(f"E2fsprogs {compiler} installed inventory changed")
        database = json.loads((evidence / f"{compiler}-compile-commands.json").read_text())
        if len(database) != actions:
            raise RuntimeError(f"E2fsprogs {compiler} compile action count changed")
        closure = source_closure(database, compiler)
        if len(closure) != 232:
            raise RuntimeError(f"E2fsprogs {compiler} compile source closure changed")
        closures.append(closure)
        builds[compiler] = {
            "compile_actions": len(database),
            "compile_sources": len(closure),
            "compile_database_sha256": sha256(evidence / f"{compiler}-compile-commands.json"),
            "installed_names": len(inventory),
        }
    if closures[0] != closures[1]:
        raise RuntimeError("E2fsprogs normalized compiler source closures differ")

    differentials = {}
    for name in ("gcc-canonical", "clang-18-canonical", "compiler"):
        path = evidence / f"{name}-differential.json"
        result = json.loads(path.read_text())
        if (result.get("programs"), result.get("cases"), result.get("passed")) != (32, 96, 96):
            raise RuntimeError(f"E2fsprogs {name} differential changed")
        differentials[name] = {"cases": 96, "passed": 96, "sha256": sha256(path)}

    upstream = {}
    for compiler in ("gcc", "clang-18"):
        path = evidence / f"{compiler}-test.log"
        counts = test_counts(path)
        status = (evidence / f"{compiler}-test.status").read_text().strip()
        if counts != (396, 10, 1) or status != "2" or "Tests failed: m_assume_storage_prezeroed" not in path.read_text(errors="replace"):
            raise RuntimeError(f"E2fsprogs {compiler} upstream suite changed: {counts}, {status}")
        upstream[compiler] = {
            "passed": 396, "skipped": 10, "environmental_failures": 1,
            "sha256": sha256(path),
        }

    resources = {"valgrind": 0, "script_syntax": 0}
    for relative in PROGRAM_PATHS:
        path = evidence / f"valgrind-{relative.replace('/', '_')}.log"
        text = path.read_text(errors="replace")
        if "ERROR SUMMARY: 0 errors" in text:
            resources["valgrind"] += 1
        elif "script syntax valid" in text:
            resources["script_syntax"] += 1
        else:
            raise RuntimeError(f"E2fsprogs resource gate changed: {relative}")
    if resources != {"valgrind": 28, "script_syntax": 4}:
        raise RuntimeError(f"E2fsprogs resource inventory changed: {resources}")

    symbols = (evidence / "symbol-gate.txt").read_text().splitlines()
    if len(symbols) != 40 or not all(line.endswith(" 1") for line in symbols):
        raise RuntimeError("E2fsprogs exported symbol gate changed")

    result = {
        "schema": 1,
        "release": "1.47.4",
        "status": "deterministic native multicall normalization complete",
        "scope": {
            "installed_names": 32, "native_names": 28,
            "native_engines": 20, "script_engines_for_later_frontends": 4,
        },
        "builds": builds,
        "differentials": differentials,
        "upstream_tests": upstream,
        "resource_gates": resources,
        "exported_symbol_checks": len(symbols),
        "manifest_sha256": sha256(evidence / "manifest.json"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result["scope"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
