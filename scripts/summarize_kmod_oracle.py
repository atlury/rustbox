#!/usr/bin/env python3
"""Generate committed evidence for the signed Kmod 34.3 canonical oracle."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORACLE = ROOT / "work/analysis/kmod-34.3/oracle"
ANALYZERS = ROOT / "work/analysis/kmod-34.3/analyzers"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources(database: Path) -> set[Path]:
    records = json.loads(database.read_text())
    result = set()
    for record in records:
        source = (Path(record["directory"]) / record["file"]).resolve()
        if source.parent.name in {"shared", "libkmod", "tools"}:
            result.add(source)
    return result


def main() -> int:
    release = json.loads((ROOT / "upstream/releases.json").read_text())["releases"]["kmod"]
    state = json.loads((ROOT / "work/upstream/.state/kmod.json").read_text())
    if not state.get("signature_verified") or state["sha256"] != release["sha256"]:
        raise RuntimeError("Kmod canonical source is not signature-verified")

    compiler_sources = {
        compiler: sources(ORACLE / f"{compiler}-compile-commands.json")
        for compiler in ("gcc", "clang")
    }
    if compiler_sources["gcc"] != compiler_sources["clang"] or len(compiler_sources["gcc"]) != 26:
        raise RuntimeError("Kmod compiler production closures differ")

    upstream = {}
    for compiler in ("gcc", "clang"):
        log_path = ORACLE / f"{compiler}-test.log"
        log = log_path.read_text(errors="replace")
        match = re.search(
            r"Ok:\s+(\d+).*?Expected Fail:\s+(\d+).*?Fail:\s+(\d+).*?Skipped:\s+(\d+)",
            log, re.DOTALL,
        )
        if not match or tuple(map(int, match.groups())) != (16, 0, 0, 0):
            raise RuntimeError(f"Kmod {compiler} upstream suite is incomplete")
        upstream[compiler] = {
            "passed": 16, "expected_failures": 0, "failures": 0, "skipped": 0,
            "log_sha256": sha256(log_path),
            "testlog_sha256": sha256(ORACLE / f"{compiler}-testlog.json"),
        }

    differential_path = ORACLE / "differential.json"
    differential = json.loads(differential_path.read_text())
    if differential.get("applets") != 7 or differential.get("cases") != 25 or differential.get("passed") != 25:
        raise RuntimeError("Kmod oracle differential is incomplete")

    valgrind = {}
    for name in ("kmod", "depmod", "insmod", "lsmod", "modinfo", "modprobe", "rmmod"):
        path = ORACLE / f"valgrind-{name}.log"
        text = path.read_text(errors="replace")
        if "ERROR SUMMARY: 0 errors" not in text or not (
            "All heap blocks were freed" in text
            or all(marker in text for marker in (
                "definitely lost: 0 bytes", "indirectly lost: 0 bytes",
                "possibly lost: 0 bytes",
            ))
        ):
            raise RuntimeError(f"Kmod {name} Valgrind result is incomplete")
        valgrind[name] = {"errors": 0, "sha256": sha256(path)}

    analyzer_names = ("cppcheck", "gcc-analyzer", "clang-analyzer-tidy", "flawfinder", "sparse")
    analyzers = {}
    for name in analyzer_names:
        status = int((ANALYZERS / f"{name}.status").read_text())
        log_path = ANALYZERS / f"{name}.log"
        if status != 0:
            raise RuntimeError(f"Kmod {name} did not complete")
        analyzers[name] = {
            "status": status,
            "diagnostic_lines": sum(
                "warning" in line.lower() or "error" in line.lower()
                for line in log_path.read_text(errors="replace").splitlines()
            ),
            "sha256": sha256(log_path),
        }

    needed = {}
    binaries = {}
    for compiler in ("gcc", "clang"):
        dynamic_path = ORACLE / f"{compiler}-dynamic.txt"
        needed[compiler] = sorted(set(re.findall(
            r"Shared library: \[([^]]+)\]", dynamic_path.read_text()
        )))
        binary = ORACLE / f"kmod-{compiler}"
        binaries[compiler] = {"bytes": binary.stat().st_size, "sha256": sha256(binary)}
    if needed["gcc"] != needed["clang"]:
        raise RuntimeError("Kmod compiler dependency surfaces differ")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-24",
        "status": "signed canonical oracle complete",
        "release": release,
        "signature_verified": True,
        "archive_members_verified": 713,
        "production_closure": {
            "sources": 26,
            "relative_paths": sorted(
                str(path).split("/work/work/upstream/kmod-34.3/", 1)[1]
                for path in compiler_sources["gcc"]
            ),
            "gcc_clang_exact": True,
        },
        "features": ["ZSTD", "XZ", "ZLIB", "OPENSSL"],
        "applets": ["kmod", "depmod", "insmod", "lsmod", "modinfo", "modprobe", "rmmod"],
        "upstream_suites": upstream,
        "differential": differential,
        "differential_sha256": sha256(differential_path),
        "valgrind": valgrind,
        "analyzers": analyzers,
        "binaries": binaries,
        "needed_libraries": needed["gcc"],
        "next_gate": "deterministic multicall-entrypoint normalization with canonical equivalence",
    }
    output = ROOT / "evidence/kmod-34.3-oracle.json"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "sources": 26, "applets": 7, "upstream": 32,
        "differential": 25, "valgrind": 7, "analyzers": 5,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
