#!/usr/bin/env python3
"""Summarize the native E2fsprogs script-frontend verification gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PROGRAMS = ("e2scrub", "e2scrub_all", "compile_et", "mk_cmds")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()

    frontends = {
        compiler: json.loads((directory / f"differential-{compiler}.json").read_text())
        for compiler in ("gcc", "clang-18")
    }
    lvm = {
        compiler: json.loads((directory / f"lvm-differential-{compiler}.json").read_text())
        for compiler in ("gcc", "clang-18")
    }
    if any(item["cases"] != 24 or item["passed"] != 24 for item in frontends.values()):
        raise RuntimeError("E2fsprogs script frontend differential is incomplete")
    for compiler, item in frontends.items():
        fresh = sum(record["case"].startswith("fresh-generator:")
                    for record in item["records"])
        repeated = sum(record["case"] == "repeat-preserves-output"
                       for record in item["records"])
        if fresh != 6 or repeated != 2:
            raise RuntimeError(f"E2fsprogs {compiler} generator isolation gate changed")
    if any(item["cases"] != 4 or item["passed"] != 4 for item in lvm.values()):
        raise RuntimeError("E2fsprogs fake-LVM orchestration differential is incomplete")

    valgrind = {}
    for program in PROGRAMS:
        path = directory / f"valgrind-{program}.log"
        text = path.read_text(errors="replace")
        if "ERROR SUMMARY: 0 errors" not in text or "All heap blocks were freed" not in text:
            raise RuntimeError(f"E2fsprogs {program} Valgrind gate is incomplete")
        valgrind[program] = sha256(path)

    analyzers = {}
    for name in ("cppcheck", "gcc-analyzer", "clang-analyzer"):
        path = directory / f"{name}.log"
        if path.read_bytes():
            raise RuntimeError(f"E2fsprogs {name} diagnostics are not empty")
        analyzers[name] = sha256(path)

    symbols = (directory / "multicall.symbols").read_text().splitlines()
    exported = sorted(
        line.split()[-1] for line in symbols
        if line.split() and line.split()[-1].startswith("rustbox_e2fsprogs_")
        and line.split()[-1].endswith("_main")
    )
    if len(exported) != 4:
        raise RuntimeError("E2fsprogs script frontend ABI changed")
    dynamic = (directory / "dynamic.txt").read_text()
    needed = [line.split("[")[1].split("]")[0] for line in dynamic.splitlines()
              if "Shared library:" in line]
    if needed != ["libc.so.6"]:
        raise RuntimeError("E2fsprogs standalone frontend dependency changed")

    result = {
        "schema": 1,
        "release": "1.47.4",
        "status": "four native script frontends verified",
        "programs": list(PROGRAMS),
        "canonical_frontend_cases": sum(item["cases"] for item in frontends.values()),
        "canonical_frontend_passed": sum(item["passed"] for item in frontends.values()),
        "fresh_isolated_generator_cases": 12,
        "repeat_preserves_inode_mtime_mode_and_bytes_cases": 4,
        "fake_lvm_orchestration_cases": sum(item["cases"] for item in lvm.values()),
        "fake_lvm_orchestration_passed": sum(item["passed"] for item in lvm.values()),
        "real_lvm_mutation_policy": "not exercised because it would mutate host block storage",
        "systemd_orchestration": "omitted by project policy; direct e2scrub dispatch is used",
        "in_binary_callbacks": ["gawk", "sed", "lsblk", "dumpe2fs", "e2fsck", "tune2fs"],
        "temporary_exec_fallbacks": ["lvs", "lvcreate", "lvremove", "udevadm", "fstrim"],
        "embedded_templates": ["et_h.awk", "et_c.awk", "ct_c.sed", "ct_c.awk"],
        "exported_symbols": exported,
        "dynamic_needed": needed,
        "valgrind_log_sha256": valgrind,
        "zero_diagnostic_analyzer_log_sha256": analyzers,
        "artifacts": {
            "gcc_bytes": (directory / "gcc/e2fsprogs-script-frontends").stat().st_size,
            "gcc_sha256": sha256(directory / "gcc/e2fsprogs-script-frontends"),
            "clang_bytes": (directory / "clang-18/e2fsprogs-script-frontends").stat().st_size,
            "clang_sha256": sha256(directory / "clang-18/e2fsprogs-script-frontends"),
            "multicall_object_bytes": (directory / "e2fsprogs-script-frontends.o").stat().st_size,
            "multicall_object_sha256": sha256(directory / "e2fsprogs-script-frontends.o"),
            "templates_object_bytes": (directory / "e2fsprogs-script-templates.o").stat().st_size,
            "templates_object_sha256": sha256(directory / "e2fsprogs-script-templates.o"),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "programs": len(PROGRAMS),
        "frontend_passed": result["canonical_frontend_passed"],
        "lvm_passed": result["fake_lvm_orchestration_passed"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
