#!/usr/bin/env python3
"""Publish reproducible evidence for the signed IPRoute2 7.3.0 oracle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


PROGRAMS = (
    "arpd", "bridge", "ctstat", "dcb", "devlink", "dpll", "genl",
    "ifstat", "ip", "lnstat", "netshaper", "nstat", "rdma", "routel",
    "rtacct", "rtmon", "rtstat", "ss", "tc", "tipc", "vdpa",
)
NATIVE_PROGRAMS = tuple(name for name in PROGRAMS if name != "routel")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_sources(database: Path, root: Path) -> tuple[list[str], int]:
    records = json.loads(database.read_text())
    sources = []
    for record in records:
        source = (Path(record["directory"]) / record["file"]).resolve()
        relative = str(source.relative_to(root))
        if relative not in sources:
            sources.append(relative)
    return sorted(sources), len(records)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.repository.resolve()
    oracle = root / "work/analysis/iproute2-7.3.0/oracle"
    analyzers = root / "work/analysis/iproute2-7.3.0/analyzers"
    release = json.loads((root / "upstream/releases.json").read_text())["releases"]["iproute2"]
    state = json.loads((root / "work/upstream/.state/iproute2.json").read_text())
    if not state.get("signature_verified") or state.get("sha256") != release["sha256"]:
        raise RuntimeError("IPRoute2 source authentication changed")

    gcc_sources, gcc_actions = relative_sources(
        oracle / "gcc-compile-commands.json", Path("/rustbox-iproute2/oracle-gcc")
    )
    clang_sources, clang_actions = relative_sources(
        oracle / "clang-18-compile-commands.json",
        Path("/rustbox-iproute2/oracle-clang-18"),
    )
    if gcc_sources != clang_sources or len(gcc_sources) != 264:
        raise RuntimeError("IPRoute2 compiler source closures changed")
    production_sources = [name for name in gcc_sources if not name.startswith("netem/")]
    if gcc_actions != 264 or clang_actions != 272 or len(production_sources) != 260:
        raise RuntimeError("IPRoute2 compile action inventory changed")

    differential_path = oracle / "differential.json"
    differential = json.loads(differential_path.read_text())
    if (
        differential.get("programs") != 21
        or differential.get("cases") != 63
        or differential.get("passed") != 63
        or not all(record.get("passed") for record in differential.get("records", []))
    ):
        raise RuntimeError("IPRoute2 canonical differential changed")

    tests = {}
    for compiler in ("gcc", "clang-18"):
        log_path = oracle / f"{compiler}-privileged-test.log"
        text = log_path.read_text(errors="replace")
        passes = len(re.findall(r"PASS", text))
        failures = len(re.findall(r"FAILED", text))
        if (
            (oracle / f"{compiler}-privileged-test.status").read_text().strip() != "0"
            or passes != 18
            or failures != 1
            or "Running ip/link/add_type_bareudp.t" not in text
            or "FAILED" not in text.split("Running ip/link/add_type_bareudp.t", 1)[1].splitlines()[0]
        ):
            raise RuntimeError(f"IPRoute2 {compiler} upstream result changed")
        tests[compiler] = {
            "tests": 19,
            "passed": passes,
            "environmental_failures": failures,
            "environmental_failure": "ip/link/add_type_bareudp.t: host kernel lacks bareudp device type",
            "sha256": sha256(log_path),
        }

    valgrind = {}
    for name in NATIVE_PROGRAMS:
        path = oracle / f"valgrind-{name}.log"
        text = path.read_text(errors="replace")
        if "ERROR SUMMARY: 0 errors" not in text:
            raise RuntimeError(f"IPRoute2 {name} Valgrind baseline changed")
        valgrind[name] = {"errors": 0, "sha256": sha256(path)}
    routel_valgrind = oracle / "valgrind-routel.log"
    if "canonical Python frontend" not in routel_valgrind.read_text():
        raise RuntimeError("IPRoute2 routel resource marker changed")

    dependencies = set()
    for name in PROGRAMS:
        text = (oracle / f"gcc-{name}.dynamic").read_text(errors="replace")
        dependencies.update(re.findall(r"Shared library: \[([^]]+)\]", text))
    if any("selinux" in name or "systemd" in name for name in dependencies):
        raise RuntimeError("IPRoute2 oracle gained an excluded dependency")

    expected_status = {
        "cppcheck.status": "0",
        "gcc-analyzer.status": "0",
        "clang-analyzer-tidy.status": "0",
        "flawfinder.status": "0",
        "sparse.status": "123",
    }
    for name, expected in expected_status.items():
        if (analyzers / name).read_text().strip() != expected:
            raise RuntimeError(f"IPRoute2 analyzer status changed: {name}")
    gcc_summary = json.loads((analyzers / "gcc-analyzer-summary.json").read_text())
    if gcc_summary.get("passed") != 260 or gcc_summary.get("failed") != 0:
        raise RuntimeError("IPRoute2 GCC analyzer replay changed")
    flawfinder = (analyzers / "flawfinder.log").read_text(errors="replace")
    hit = re.search(r"^Hits = (\d+)$", flawfinder, re.MULTILINE)
    if not hit or int(hit.group(1)) != 1332:
        raise RuntimeError("IPRoute2 Flawfinder baseline changed")

    build_configuration = {
        "shared_plugins": False,
        "selinux": False,
        "libtirpc": True,
        "libbpf": "1.3.0",
        "libelf": True,
        "libmnl": True,
        "berkeley_db": True,
        "libcap": True,
        "xtables": True,
    }
    for compiler in ("gcc", "clang"):
        build_log = oracle / ("gcc-build.log" if compiler == "gcc" else "clang-build.log")
        text = build_log.read_text(errors="replace")
        for marker in (
            "SELinux support: no", "libtirpc support: yes", "libbpf support: yes",
            "ELF support: yes", "libmnl support: yes", "Berkeley DB: yes",
            "libcap support: yes", "IPT\tusing xtables",
        ):
            if marker not in text:
                raise RuntimeError(f"IPRoute2 {compiler} configuration changed: {marker}")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-24",
        "release": release,
        "status": "signed canonical IPRoute2 oracle complete",
        "source_authentication": state,
        "scope": {
            "public_names": list(PROGRAMS),
            "public_name_count": 21,
            "native_engines": 18,
            "native_aliases": {"ctstat": "lnstat", "rtstat": "lnstat"},
            "script_frontends": ["routel"],
            "compiled_sources": 264,
            "production_utility_sources": 260,
            "excluded_build_helpers": [
                "netem/maketable.c", "netem/normal.c", "netem/pareto.c",
                "netem/paretonormal.c",
            ],
            "source_list_sha256": hashlib.sha256(
                ("\n".join(gcc_sources) + "\n").encode()
            ).hexdigest(),
        },
        "build_configuration": build_configuration,
        "compilers": {
            "gcc": {"compile_actions": gcc_actions, "sources": len(gcc_sources)},
            "clang-18": {"compile_actions": clang_actions, "sources": len(clang_sources)},
        },
        "dependencies": sorted(dependencies),
        "excluded_dependencies": ["SELinux", "systemd"],
        "upstream_tests": tests,
        "differential": {
            "cases": 63,
            "passed": 63,
            "physical_argv0_normalized": True,
            "sha256": sha256(differential_path),
        },
        "valgrind": {
            "native_programs": valgrind,
            "routel": {"kind": "canonical Python frontend", "sha256": sha256(routel_valgrind)},
        },
        "static_analysis": {
            "production_sources": 260,
            "cppcheck": {"status": 0, "sha256": sha256(analyzers / "cppcheck.log")},
            "gcc_fanalyzer": {**gcc_summary, "sha256": sha256(analyzers / "gcc-analyzer.log")},
            "clang_analyzer_tidy": {"status": 0, "sha256": sha256(analyzers / "clang-analyzer-tidy.log")},
            "flawfinder": {"status": 0, "hits": 1332, "sha256": sha256(analyzers / "flawfinder.log")},
            "sparse": {"status": 123, "baseline_only": True, "sha256": sha256(analyzers / "sparse.log")},
        },
        "next_gate": "complete deterministic entrypoint normalization and strict C2Rust translation",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"programs": 21, "sources": 260, "cases": 63}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
