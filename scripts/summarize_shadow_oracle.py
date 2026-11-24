#!/usr/bin/env python3
"""Generate committed evidence for the signed Shadow 4.20.4 oracle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


PROGRAMS = (
    "chage", "chfn", "chgpasswd", "chpasswd", "chsh", "faillog",
    "getsubids", "gpasswd", "groupadd", "groupdel", "groupmod", "grpck",
    "grpconv", "grpunconv", "lastlog", "login", "newgidmap", "newgrp",
    "newuidmap", "newusers", "nologin", "passwd", "pwck", "pwconv",
    "pwunconv", "su", "useradd", "userdel", "usermod", "vipw", "sg",
    "vigr",
)
ANALYZERS = ("cppcheck", "gcc-analyzer", "clang-analyzer-tidy", "flawfinder", "sparse")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def production_sources(database: Path, signed: Path) -> set[Path]:
    result = set()
    for record in json.loads(database.read_text()):
        source = Path(record["file"]).resolve()
        if source.is_relative_to(signed) and "tests" not in source.parts:
            result.add(source)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--gcc-root", required=True, type=Path)
    parser.add_argument("--clang-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.repository.resolve()
    signed = root / "work/upstream/shadow-4.20.4"
    oracle = root / "work/analysis/shadow-4.20.4/oracle"
    analyzer_root = root / "work/analysis/shadow-4.20.4/analyzers"
    release = json.loads((root / "upstream/releases.json").read_text())["releases"]["shadow"]
    state = json.loads((root / "work/upstream/.state/shadow.json").read_text())
    if not state.get("signature_verified") or state.get("sha256") != release["sha256"]:
        raise RuntimeError("Shadow canonical source is not signature-verified")

    databases = {
        "gcc": oracle / "gcc-compile-commands.json",
        "clang": oracle / "clang-18-compile-commands.json",
    }
    closures = {name: production_sources(path, signed) for name, path in databases.items()}
    action_counts = {name: len(json.loads(path.read_text())) for name, path in databases.items()}
    if (
        closures["gcc"] != closures["clang"]
        or len(closures["gcc"]) != 201
        or action_counts != {"gcc": 201, "clang": 201}
    ):
        raise RuntimeError("Shadow compiler production closures differ")

    upstream = {}
    for compiler, stem in (("gcc", "gcc"), ("clang", "clang-18")):
        log_path = oracle / f"{stem}-test.log"
        log = log_path.read_text(errors="replace")
        summary = re.search(
            r"# TOTAL:\s+(\d+).*?# PASS:\s+(\d+).*?# SKIP:\s+(\d+).*?"
            r"# XFAIL:\s+(\d+).*?# FAIL:\s+(\d+).*?# XPASS:\s+(\d+).*?# ERROR:\s+(\d+)",
            log, re.DOTALL,
        )
        if (
            int((oracle / f"{stem}-test.status").read_text()) != 0
            or summary is None
            or tuple(map(int, summary.groups())) != (8, 8, 0, 0, 0, 0, 0)
        ):
            raise RuntimeError(f"Shadow {compiler} upstream suite is incomplete")
        upstream[compiler] = {"passes": 8, "failures": 0, "log_sha256": sha256(log_path)}

    differential_path = oracle / "differential.json"
    differential = json.loads(differential_path.read_text())
    if (
        differential.get("programs") != 32
        or differential.get("cases") != 79
        or differential.get("stateful_cases") != 8
        or differential.get("passed") != 79
    ):
        raise RuntimeError("Shadow oracle differential is incomplete")

    valgrind = {}
    for name in PROGRAMS:
        path = oracle / f"valgrind-{name}.log"
        text = path.read_text(errors="replace")
        match = re.search(r"ERROR SUMMARY: (\d+) errors", text)
        if match is None:
            raise RuntimeError(f"Shadow {name} Valgrind result is incomplete")
        errors = int(match.group(1))
        if name == "gpasswd":
            required = (
                "ERROR SUMMARY: 6 errors from 6 contexts",
                "definitely lost: 48 bytes in 1 blocks",
                "indirectly lost: 28 bytes in 5 blocks",
                "possibly lost: 0 bytes in 0 blocks",
            )
            if not all(marker in text for marker in required):
                raise RuntimeError("Shadow gpasswd canonical allocation baseline changed")
            valgrind[name] = {
                "errors": 6, "definitely_lost_bytes": 48,
                "indirectly_lost_bytes": 28, "sha256": sha256(path),
            }
        else:
            if errors != 0:
                raise RuntimeError(f"Shadow {name} introduced a Valgrind error")
            valgrind[name] = {"errors": 0, "sha256": sha256(path)}

    analyzers = {}
    for name in ANALYZERS:
        status = int((analyzer_root / f"{name}.status").read_text())
        log_path = analyzer_root / f"{name}.log"
        if status != 0:
            raise RuntimeError(f"Shadow {name} did not complete")
        analyzers[name] = {
            "status": 0,
            "diagnostic_lines": sum(
                "warning" in line.lower() or "error" in line.lower()
                for line in log_path.read_text(errors="replace").splitlines()
            ),
            "sha256": sha256(log_path),
        }

    roots = {"gcc": args.gcc_root.resolve(), "clang": args.clang_root.resolve()}
    binaries = {}
    dependencies = {}
    for compiler, program_root in roots.items():
        stem = "gcc" if compiler == "gcc" else "clang-18"
        binaries[compiler] = {}
        dependencies[compiler] = {}
        for name in PROGRAMS:
            binary = program_root / name
            binaries[compiler][name] = {"bytes": binary.stat().st_size, "sha256": sha256(binary)}
            dynamic = (oracle / f"{stem}-{name}.dynamic").read_text()
            dependencies[compiler][name] = sorted(set(re.findall(r"Shared library: \[([^]]+)\]", dynamic)))
            if not set(dependencies[compiler][name]).issubset({"libc.so.6", "libcrypt.so.1"}):
                raise RuntimeError(f"Shadow {name} has an excluded runtime dependency")
    dependency_deltas = {
        name: {
            "gcc_only": sorted(set(dependencies["gcc"][name]) - set(dependencies["clang"][name])),
            "clang_only": sorted(set(dependencies["clang"][name]) - set(dependencies["gcc"][name])),
        }
        for name in PROGRAMS
        if dependencies["gcc"][name] != dependencies["clang"][name]
    }
    if dependency_deltas != {"getsubids": {"gcc_only": [], "clang_only": ["libcrypt.so.1"]}}:
        raise RuntimeError(f"Shadow compiler dependency delta changed: {dependency_deltas}")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-24",
        "status": "signed canonical Shadow oracle complete",
        "release": release,
        "signature_verified": True,
        "archive_members_verified": 15201,
        "profile": {
            "systemd": False, "selinux": False, "pam": False, "audit": False,
            "acl": False, "libbsd": False, "shared_libraries": False,
            "shadow_group": True, "subordinate_ids": True, "yescrypt": True,
        },
        "programs": list(PROGRAMS),
        "production_closure": {
            "compile_actions": 201,
            "sources": 201,
            "gcc_clang_exact": True,
            "relative_paths": sorted(str(path.relative_to(signed)) for path in closures["gcc"]),
        },
        "upstream_suites": upstream,
        "differential": differential,
        "differential_sha256": sha256(differential_path),
        "valgrind": valgrind,
        "analyzers": analyzers,
        "binaries": binaries,
        "needed_libraries": dependencies["gcc"],
        "compiler_dependency_deltas": dependency_deltas,
        "next_gate": "deterministic 32-entrypoint normalization with canonical equivalence",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "programs": 32, "sources": 201, "upstream_passes": 16,
        "differential": 79, "valgrind_paths": 32, "analyzers": 5,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
