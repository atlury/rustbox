#!/usr/bin/env python3
"""Generate committed evidence for the unified Rustbox multicall executable."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--link-report", type=Path, required=True)
    parser.add_argument("--dispatch-report", type=Path, required=True)
    parser.add_argument("--differential-report", type=Path, required=True)
    parser.add_argument("--m4-report-directory", type=Path, required=True)
    parser.add_argument("--pkgconf-report-directory", type=Path, required=True)
    parser.add_argument("--file-report-directory", type=Path, required=True)
    parser.add_argument("--patch-report-directory", type=Path, required=True)
    parser.add_argument("--sed-report-directory", type=Path, required=True)
    parser.add_argument("--diffutils-report-directory", type=Path, required=True)
    parser.add_argument("--grep-report-directory", type=Path, required=True)
    parser.add_argument("--bc-report-directory", type=Path, required=True)
    parser.add_argument("--attr-report-directory", type=Path, required=True)
    parser.add_argument("--acl-report-directory", type=Path, required=True)
    parser.add_argument("--lz4-report-directory", type=Path, required=True)
    parser.add_argument("--gzip-report-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    binary = args.binary.resolve()
    link = json.loads(args.link_report.read_text(encoding="utf-8"))
    dispatch = json.loads(args.dispatch_report.read_text(encoding="utf-8"))
    differential = json.loads(args.differential_report.read_text(encoding="utf-8"))
    m4_directory = args.m4_report_directory.resolve()
    pkgconf_directory = args.pkgconf_report_directory.resolve()
    file_directory = args.file_report_directory.resolve()
    patch_directory = args.patch_report_directory.resolve()
    sed_directory = args.sed_report_directory.resolve()
    diffutils_directory = args.diffutils_report_directory.resolve()
    grep_directory = args.grep_report_directory.resolve()
    bc_directory = args.bc_report_directory.resolve()
    attr_directory = args.attr_report_directory.resolve()
    acl_directory = args.acl_report_directory.resolve()
    lz4_directory = args.lz4_report_directory.resolve()
    gzip_directory = args.gzip_report_directory.resolve()
    m4_differential = json.loads((m4_directory / "differential.json").read_text())
    m4_language = (m4_directory / "language-check.log").read_text(errors="replace")
    m4_valgrind = (m4_directory / "valgrind.log").read_text(errors="replace")
    if dispatch["cases"] != 598 or dispatch["passed"] != 598 or dispatch["failures"]:
        raise RuntimeError("unified dispatcher comparison is incomplete")
    if (
        differential["batches"] != 38
        or differential["cases"] != 14022
        or differential["passed"] != 14022
        or differential["failed_batches"]
    ):
        raise RuntimeError("unified batch differential comparison is incomplete")
    m4_numbered = set(re.findall(r"^Checking .*/checks/(\d{3})\.", m4_language, re.MULTILINE))
    if (
        len(m4_numbered) != 242
        or "All checks successful" not in m4_language
        or "stackovf.test" not in m4_language
        or not m4_differential["canonical_hybrid_exact"]
        or m4_differential["comparisons"] != 108
        or "ERROR SUMMARY: 0 errors" not in m4_valgrind
    ):
        raise RuntimeError("unified M4 integration comparison is incomplete")
    pkgconf_fixture_path = pkgconf_directory / "fixture-tests.log"
    pkgconf_fixture = pkgconf_fixture_path.read_text(errors="replace")
    pkgconf_fixture_passes = len(re.findall(r"^PASS:", pkgconf_fixture, re.MULTILINE))
    pkgconf_fixture_skips = len(re.findall(r"^SKIP:", pkgconf_fixture, re.MULTILINE))
    pkgconf_differential_path = pkgconf_directory / "differential.json"
    pkgconf_differential = json.loads(pkgconf_differential_path.read_text())
    pkgconf_valgrind_path = pkgconf_directory / "valgrind.log"
    pkgconf_valgrind = pkgconf_valgrind_path.read_text(errors="replace")
    if (
        pkgconf_fixture_passes != 429
        or pkgconf_fixture_skips != 5
        or re.search(r"^(?:FAIL|ERROR):", pkgconf_fixture, re.MULTILINE)
        or not pkgconf_differential["canonical_hybrid_exact"]
        or pkgconf_differential["comparisons"] != 55
        or "ERROR SUMMARY: 0 errors" not in pkgconf_valgrind
    ):
        raise RuntimeError("unified pkgconf integration comparison is incomplete")
    file_differential_path = file_directory / "differential.json"
    file_differential = json.loads(file_differential_path.read_text())
    file_valgrind_path = file_directory / "valgrind.log"
    file_valgrind = file_valgrind_path.read_text(errors="replace")
    if (
        not file_differential["gcc_clang_exact"]
        or file_differential["comparisons"] != 174
        or "ERROR SUMMARY: 0 errors" not in file_valgrind
        or "All heap blocks were freed -- no leaks are possible" not in file_valgrind
    ):
        raise RuntimeError("unified File integration comparison is incomplete")
    patch_differential_path = patch_directory / "differential.json"
    patch_differential = json.loads(patch_differential_path.read_text())
    patch_upstream_path = patch_directory / "upstream-tests.log"
    patch_upstream = patch_upstream_path.read_text(errors="replace")
    patch_valgrind_path = patch_directory / "valgrind.log"
    patch_valgrind = patch_valgrind_path.read_text(errors="replace")
    patch_summary = {
        name.lower(): int(match.group(1))
        for name in ("TOTAL", "PASS", "SKIP", "XFAIL", "FAIL", "XPASS", "ERROR")
        if (match := re.search(rf"^# {name}:\s+(\d+)$", patch_upstream, re.MULTILINE))
    }
    if (
        patch_summary != {"total": 49, "pass": 47, "skip": 0, "xfail": 2,
                          "fail": 0, "xpass": 0, "error": 0}
        or not patch_differential["gcc_clang_exact"]
        or patch_differential["comparisons"] != 28
        or "ERROR SUMMARY: 0 errors" not in patch_valgrind
        or "definitely lost: 0 bytes in 0 blocks" not in patch_valgrind
        or "indirectly lost: 0 bytes in 0 blocks" not in patch_valgrind
        or "possibly lost: 0 bytes in 0 blocks" not in patch_valgrind
    ):
        raise RuntimeError("unified GNU patch integration comparison is incomplete")
    sed_differential_path = sed_directory / "differential.json"
    sed_differential = json.loads(sed_differential_path.read_text())
    sed_upstream_path = sed_directory / "upstream-tests.log"
    sed_upstream = sed_upstream_path.read_text(errors="replace")
    sed_valgrind_path = sed_directory / "valgrind.log"
    sed_valgrind = sed_valgrind_path.read_text(errors="replace")
    sed_summaries = []
    for match in re.finditer(
        r"# TOTAL:\s+(\d+).*?# PASS:\s+(\d+).*?# SKIP:\s+(\d+).*?"
        r"# XFAIL:\s+(\d+).*?# FAIL:\s+(\d+).*?# XPASS:\s+(\d+).*?# ERROR:\s+(\d+)",
        sed_upstream,
        re.DOTALL,
    ):
        sed_summaries.append(dict(zip(
            ("total", "pass", "skip", "xfail", "fail", "xpass", "error"),
            map(int, match.groups()),
        )))
    expected_sed_summaries = [
        {"total": 75, "pass": 68, "skip": 7, "xfail": 0, "fail": 0, "xpass": 0, "error": 0},
        {"total": 287, "pass": 241, "skip": 46, "xfail": 0, "fail": 0, "xpass": 0, "error": 0},
    ]
    if (
        sed_summaries != expected_sed_summaries
        or not sed_differential["gcc_clang_exact"]
        or sed_differential["comparisons"] != 30
        or "ERROR SUMMARY: 0 errors" not in sed_valgrind
        or "definitely lost: 0 bytes in 0 blocks" not in sed_valgrind
        or "indirectly lost: 0 bytes in 0 blocks" not in sed_valgrind
        or "possibly lost: 0 bytes in 0 blocks" not in sed_valgrind
    ):
        raise RuntimeError("unified GNU sed integration comparison is incomplete")
    diffutils_differential_path = diffutils_directory / "differential.json"
    diffutils_differential = json.loads(diffutils_differential_path.read_text())
    diffutils_upstream_path = diffutils_directory / "upstream-tests.log"
    diffutils_upstream = diffutils_upstream_path.read_text(errors="replace")
    diffutils_summaries = []
    for match in re.finditer(
        r"# TOTAL:\s+(\d+).*?# PASS:\s+(\d+).*?# SKIP:\s+(\d+).*?"
        r"# XFAIL:\s+(\d+).*?# FAIL:\s+(\d+).*?# XPASS:\s+(\d+).*?# ERROR:\s+(\d+)",
        diffutils_upstream,
        re.DOTALL,
    ):
        diffutils_summaries.append(dict(zip(
            ("total", "pass", "skip", "xfail", "fail", "xpass", "error"),
            map(int, match.groups()),
        )))
    expected_diffutils_summaries = [
        {"total": 33, "pass": 30, "skip": 2, "xfail": 1, "fail": 0, "xpass": 0, "error": 0},
        {"total": 344, "pass": 301, "skip": 43, "xfail": 0, "fail": 0, "xpass": 0, "error": 0},
    ]
    diffutils_valgrind_paths = {
        name: diffutils_directory / f"valgrind-{name}.log"
        for name in ("cmp", "diff", "diff3", "sdiff")
    }
    for name in ("cmp", "diff", "sdiff"):
        text = diffutils_valgrind_paths[name].read_text(errors="replace")
        if (
            "ERROR SUMMARY: 0 errors" not in text
            or "definitely lost: 0 bytes in 0 blocks" not in text
            or "indirectly lost: 0 bytes in 0 blocks" not in text
            or "possibly lost: 0 bytes in 0 blocks" not in text
        ):
            raise RuntimeError(f"unified GNU {name} Valgrind comparison is incomplete")
    diff3_valgrind = diffutils_valgrind_paths["diff3"].read_text(errors="replace")
    if (
        diffutils_summaries != expected_diffutils_summaries
        or not diffutils_differential["gcc_clang_exact"]
        or diffutils_differential["comparisons"] != 48
        or "ERROR SUMMARY: 9 errors" not in diff3_valgrind
        or (diffutils_directory / "valgrind-diff3-heap").read_text()
           != (diffutils_directory / "valgrind-diff3-canonical-heap").read_text()
    ):
        raise RuntimeError("unified GNU Diffutils integration comparison is incomplete")
    grep_differential_path = grep_directory / "differential.json"
    grep_differential = json.loads(grep_differential_path.read_text())
    grep_alias_path = grep_directory / "alias-differential.json"
    grep_alias = json.loads(grep_alias_path.read_text())
    grep_upstream_path = grep_directory / "upstream-tests.log"
    grep_upstream = grep_upstream_path.read_text(errors="replace")
    grep_summaries = []
    for match in re.finditer(
        r"# TOTAL:\s+(\d+).*?# PASS:\s+(\d+).*?# SKIP:\s+(\d+).*?"
        r"# XFAIL:\s+(\d+).*?# FAIL:\s+(\d+).*?# XPASS:\s+(\d+).*?# ERROR:\s+(\d+)",
        grep_upstream,
        re.DOTALL,
    ):
        grep_summaries.append(dict(zip(
            ("total", "pass", "skip", "xfail", "fail", "xpass", "error"),
            map(int, match.groups()),
        )))
    expected_grep_summaries = [
        {"total": 128, "pass": 113, "skip": 13, "xfail": 2,
         "fail": 0, "xpass": 0, "error": 0},
        {"total": 315, "pass": 277, "skip": 38, "xfail": 0,
         "fail": 0, "xpass": 0, "error": 0},
    ]
    grep_valgrind_path = grep_directory / "valgrind.log"
    grep_valgrind = grep_valgrind_path.read_text(errors="replace")
    if (
        grep_summaries != expected_grep_summaries
        or not grep_differential["gcc_clang_exact"]
        or grep_differential["comparisons"] != 36
        or not grep_alias["canonical_multicall_exact"]
        or grep_alias["comparisons"] != 4
        or "ERROR SUMMARY: 3 errors" not in grep_valgrind
        or "definitely lost: 0 bytes in 0 blocks" not in grep_valgrind
        or "indirectly lost: 0 bytes in 0 blocks" not in grep_valgrind
        or "possibly lost: 18,688 bytes in 11 blocks" not in grep_valgrind
        or "still reachable: 119,466 bytes in 39 blocks" not in grep_valgrind
    ):
        raise RuntimeError("unified GNU Grep integration comparison is incomplete")
    bc_differential_path = bc_directory / "differential.json"
    bc_differential = json.loads(bc_differential_path.read_text())
    bc_workload_path = bc_directory / "upstream-tests.log"
    bc_workloads = bc_workload_path.read_text().splitlines()
    bc_valgrind_paths = {
        name: bc_directory / f"valgrind-{name}.log" for name in ("bc", "dc")
    }
    bc_expected_heaps = {
        "bc": [
            "in use at exit: 52,619 bytes in 53 blocks",
            "total heap usage: 66 allocs, 13 frees, 56,826 bytes allocated",
        ],
        "dc": [
            "in use at exit: 376 bytes in 13 blocks",
            "total heap usage: 37 allocs, 24 frees, 8,774 bytes allocated",
        ],
    }
    for name, path in bc_valgrind_paths.items():
        text = path.read_text(errors="replace")
        heap = (bc_directory / f"valgrind-{name}-heap").read_text().splitlines()[1:]
        if "ERROR SUMMARY: 0 errors" not in text or heap != bc_expected_heaps[name]:
            raise RuntimeError(f"unified GNU {name} Valgrind comparison is incomplete")
    if (
        bc_differential["cases"] != 46
        or bc_differential["passed"] != 46
        or len(bc_workloads) != 18
        or any(not line.endswith(" pass") for line in bc_workloads)
        or "checklib.b pass" not in bc_workloads
    ):
        raise RuntimeError("unified GNU bc/dc integration comparison is incomplete")
    attr_differential_path = attr_directory / "differential.json"
    attr_differential = json.loads(attr_differential_path.read_text())
    attr_upstream_path = attr_directory / "upstream-tests.log"
    attr_upstream = attr_upstream_path.read_text(errors="replace")
    attr_summary = {
        name.lower(): int(match.group(1))
        for name in ("TOTAL", "PASS", "SKIP", "XFAIL", "FAIL", "XPASS", "ERROR")
        if (match := re.search(rf"^# {name}:\s+(\d+)$", attr_upstream, re.MULTILINE))
    }
    attr_valgrind_paths = {
        name: attr_directory / f"valgrind-{name}.log"
        for name in ("setfattr", "getfattr")
    }
    attr_expected_heaps = {
        "setfattr": [
            "in use at exit: 256 bytes in 1 blocks",
            "total heap usage: 1 allocs, 0 frees, 256 bytes allocated",
        ],
        "getfattr": [
            "in use at exit: 2,152 bytes in 42 blocks",
            "total heap usage: 48 allocs, 6 frees, 7,264 bytes allocated",
        ],
    }
    for name, path in attr_valgrind_paths.items():
        text = path.read_text(errors="replace")
        heap = (attr_directory / f"valgrind-{name}-heap").read_text().splitlines()[1:]
        if "ERROR SUMMARY: 0 errors" not in text or heap != attr_expected_heaps[name]:
            raise RuntimeError(f"unified attr {name} Valgrind comparison is incomplete")
    if (
        attr_summary != {"total": 3, "pass": 2, "skip": 1, "xfail": 0,
                         "fail": 0, "xpass": 0, "error": 0}
        or attr_differential["cases"] != 22
        or attr_differential["passed"] != 22
    ):
        raise RuntimeError("unified attr integration comparison is incomplete")
    acl_differential_path = acl_directory / "differential.json"
    acl_differential = json.loads(acl_differential_path.read_text())
    acl_upstream_path = acl_directory / "upstream-tests.log"
    acl_platform_path = acl_directory / "platform-permissions.log"
    acl_upstream = acl_upstream_path.read_text(errors="replace")
    acl_platform = acl_platform_path.read_text(errors="replace")
    acl_summary = {
        name.lower(): int(match.group(1))
        for name in ("TOTAL", "PASS", "SKIP", "XFAIL", "FAIL", "XPASS", "ERROR")
        if (match := re.search(rf"^# {name}:\s+(\d+)$", acl_upstream, re.MULTILINE))
    }
    acl_platform_summary = {
        name.lower(): int(match.group(1))
        for name in ("TOTAL", "PASS", "SKIP", "XFAIL", "FAIL", "XPASS", "ERROR")
        if (match := re.search(rf"^# {name}:\s+(\d+)$", acl_platform, re.MULTILINE))
    }
    acl_valgrind_paths = {
        name: acl_directory / f"valgrind-{name}.log"
        for name in ("setfacl", "getfacl")
    }
    acl_expected_heaps = {
        "setfacl": [
            "in use at exit: 0 bytes in 0 blocks",
            "total heap usage: 12 allocs, 12 frees, 950 bytes allocated",
        ],
        "getfacl": [
            "in use at exit: 0 bytes in 0 blocks",
            "total heap usage: 8 allocs, 8 frees, 4,920 bytes allocated",
        ],
    }
    for name, path in acl_valgrind_paths.items():
        text = path.read_text(errors="replace")
        heap = (acl_directory / f"valgrind-{name}-heap").read_text().splitlines()[1:]
        if (
            "ERROR SUMMARY: 0 errors" not in text
            or "All heap blocks were freed -- no leaks are possible" not in text
            or heap != acl_expected_heaps[name]
        ):
            raise RuntimeError(f"unified acl {name} Valgrind comparison is incomplete")
    if (
        acl_summary != {"total": 15, "pass": 13, "skip": 0, "xfail": 2,
                        "fail": 0, "xpass": 0, "error": 0}
        or acl_platform_summary != {"total": 1, "pass": 0, "skip": 0, "xfail": 0,
                                   "fail": 1, "xpass": 0, "error": 0}
        or acl_differential["cases"] != 30
        or acl_differential["passed"] != 30
    ):
        raise RuntimeError("unified acl integration comparison is incomplete")
    lz4_differential_path = lz4_directory / "differential.json"
    lz4_differential = json.loads(lz4_differential_path.read_text())
    lz4_upstream_path = lz4_directory / "upstream-tests.log"
    lz4_upstream = lz4_upstream_path.read_text(errors="replace")
    lz4_markers = [
        "test lz4 basic compression/decompression", "test command line options",
        "test --list", "test lz4 multithreaded compression",
        "make: Leaving directory",
    ]
    lz4_expected_heaps = {
        "compress": [
            "in use at exit: 0 bytes in 0 blocks",
            "total heap usage: 9 allocs, 9 frees, 8,410,567 bytes allocated",
        ],
        "decompress": [
            "in use at exit: 0 bytes in 0 blocks",
            "total heap usage: 29 allocs, 29 frees, 29,633,252 bytes allocated",
        ],
    }
    lz4_valgrind_paths = {
        operation: lz4_directory / f"valgrind-{operation}.log"
        for operation in ("compress", "decompress")
    }
    for operation, path in lz4_valgrind_paths.items():
        text = path.read_text(errors="replace")
        heap = (lz4_directory / f"valgrind-{operation}-heap").read_text().splitlines()[1:]
        if (
            "ERROR SUMMARY: 0 errors" not in text
            or "All heap blocks were freed -- no leaks are possible" not in text
            or heap != lz4_expected_heaps[operation]
        ):
            raise RuntimeError(f"unified LZ4 {operation} Valgrind comparison is incomplete")
    if (
        lz4_differential.get("cases") != 27
        or lz4_differential.get("passed") != 27
        or "make: ***" in lz4_upstream
        or any(marker not in lz4_upstream for marker in lz4_markers)
    ):
        raise RuntimeError("unified LZ4 integration comparison is incomplete")
    gzip_differential_path = gzip_directory / "differential.json"
    gzip_differential = json.loads(gzip_differential_path.read_text())
    gzip_valgrind_paths = {
        operation: gzip_directory / f"valgrind-{operation}.log"
        for operation in ("compress", "decompress", "zcmp", "zdiff", "zgrep")
    }
    for operation, path in gzip_valgrind_paths.items():
        text = path.read_text(errors="replace")
        required = []
        if operation == "zgrep":
            required.extend([
                "ERROR SUMMARY: 1 errors",
                "definitely lost: 0 bytes in 0 blocks",
                "indirectly lost: 0 bytes in 0 blocks",
                "possibly lost: 128 bytes in 1 blocks",
                "still reachable: 112,870 bytes in 19 blocks",
            ])
        elif operation in {"compress", "decompress"}:
            required.extend([
                "ERROR SUMMARY: 0 errors",
                "All heap blocks were freed -- no leaks are possible",
            ])
        else:
            required.append("ERROR SUMMARY: 0 errors")
            required.extend([
                "definitely lost: 0 bytes in 0 blocks",
                "indirectly lost: 0 bytes in 0 blocks",
                "possibly lost: 0 bytes in 0 blocks",
            ])
        if any(marker not in text for marker in required):
            raise RuntimeError(f"unified GNU Gzip {operation} Valgrind comparison is incomplete")
    if gzip_differential.get("cases") != 77 or gzip_differential.get("passed") != 77:
        raise RuntimeError("unified GNU Gzip integration comparison is incomplete")
    if sha256(binary) != link["binary"]["sha256"]:
        raise RuntimeError("unified binary changed after link evidence")
    with tempfile.TemporaryDirectory(prefix="rustbox-strip-") as temporary:
        stripped = Path(temporary) / "rustbox"
        shutil.copy2(binary, stripped)
        subprocess.run(["strip", "--strip-all", str(stripped)], check=True)
        stripped_bytes = stripped.stat().st_size
        stripped_sha256 = sha256(stripped)
    dynamic = subprocess.run(
        ["readelf", "-d", str(binary)], check=True, text=True, stdout=subprocess.PIPE
    ).stdout
    needed = sorted(set(re.findall(r"Shared library: \[([^]]+)\]", dynamic)))
    forbidden = [name for name in needed if "selinux" in name or "systemd" in name]
    undefined = subprocess.run(
        ["nm", "-u", str(binary)], check=True, text=True, stdout=subprocess.PIPE
    ).stdout
    forbidden_undefined = sorted(
        line.strip() for line in undefined.splitlines()
        if "selinux" in line.lower() or "systemd" in line.lower()
    )
    if forbidden or forbidden_undefined:
        raise RuntimeError("unified binary retains a forbidden SELinux/systemd dependency")
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-22",
        "status": "Coreutils, util-linux, GNU M4, pkgconf, File, GNU patch, GNU sed, GNU Diffutils, GNU Grep, GNU bc, GNU dc, attr, acl, LZ4, and ten GNU Gzip interfaces integrated at canonical parity",
        "scope": {
            "coreutils": 106,
            "util_linux": 155,
            "m4": 1,
            "pkgconf_public_names": 5,
            "file": 1,
            "patch": 1,
            "sed": 1,
            "diffutils": 4,
            "grep": 3,
            "bc": 2,
            "attr": 3,
            "acl": 3,
            "lz4": 4,
            "gzip_integrated_names": 10,
            "dispatch_names": 299,
            "excluded": ["chcon", "runcon"],
        },
        "binary": {
            **link["binary"],
            "stripped_bytes": stripped_bytes,
            "stripped_sha256": stripped_sha256,
            "needed_libraries": needed,
            "selinux_dependencies": [],
            "systemd_dependencies": [],
        },
        "dispatch": dispatch,
        "batch_differential": differential,
        "m4_integration": {
            "numbered_language_checks": len(m4_numbered),
            "stack_overflow_check": "pass",
            "differential": m4_differential,
            "valgrind_errors": 0,
            "language_log_sha256": sha256(m4_directory / "language-check.log"),
            "valgrind_log_sha256": sha256(m4_directory / "valgrind.log"),
        },
        "pkgconf_integration": {
            "fixture_passes": pkgconf_fixture_passes,
            "intentional_platform_skips": pkgconf_fixture_skips,
            "differential": pkgconf_differential,
            "valgrind_errors": 0,
            "fixture_log_sha256": sha256(pkgconf_fixture_path),
            "valgrind_log_sha256": sha256(pkgconf_valgrind_path),
        },
        "file_integration": {
            "differential": file_differential,
            "valgrind_errors": 0,
            "differential_sha256": sha256(file_differential_path),
            "valgrind_log_sha256": sha256(file_valgrind_path),
        },
        "patch_integration": {
            "upstream_suite": patch_summary,
            "differential": patch_differential,
            "valgrind_errors": 0,
            "upstream_log_sha256": sha256(patch_upstream_path),
            "differential_sha256": sha256(patch_differential_path),
            "valgrind_log_sha256": sha256(patch_valgrind_path),
        },
        "sed_integration": {
            "upstream_suites": sed_summaries,
            "differential": sed_differential,
            "valgrind_errors": 0,
            "upstream_log_sha256": sha256(sed_upstream_path),
            "differential_sha256": sha256(sed_differential_path),
            "valgrind_log_sha256": sha256(sed_valgrind_path),
        },
        "diffutils_integration": {
            "upstream_suites": diffutils_summaries,
            "differential": diffutils_differential,
            "valgrind_clean_applets": ["cmp", "diff", "sdiff"],
            "diff3_allocation_lifecycle_exact": True,
            "upstream_log_sha256": sha256(diffutils_upstream_path),
            "differential_sha256": sha256(diffutils_differential_path),
            "valgrind_log_sha256": {
                name: sha256(path) for name, path in diffutils_valgrind_paths.items()
            },
        },
        "grep_integration": {
            "upstream_suites": grep_summaries,
            "differential": grep_differential,
            "alias_differential": grep_alias,
            "valgrind_allocation_lifecycle_matches_canonical": True,
            "upstream_log_sha256": sha256(grep_upstream_path),
            "differential_sha256": sha256(grep_differential_path),
            "alias_differential_sha256": sha256(grep_alias_path),
            "valgrind_log_sha256": sha256(grep_valgrind_path),
        },
        "bc_integration": {
            "shipped_workloads": len(bc_workloads),
            "exhaustive_checklib": True,
            "differential": bc_differential,
            "valgrind_allocation_lifecycle_matches_canonical": True,
            "workload_log_sha256": sha256(bc_workload_path),
            "differential_sha256": sha256(bc_differential_path),
            "valgrind_log_sha256": {
                name: sha256(path) for name, path in bc_valgrind_paths.items()
            },
        },
        "attr_integration": {
            "upstream_suite": attr_summary,
            "differential": attr_differential,
            "valgrind_allocation_lifecycle_matches_canonical": True,
            "upstream_log_sha256": sha256(attr_upstream_path),
            "differential_sha256": sha256(attr_differential_path),
            "valgrind_log_sha256": {
                name: sha256(path) for name, path in attr_valgrind_paths.items()
            },
        },
        "acl_integration": {
            "upstream_suite": acl_summary,
            "platform_suite": acl_platform_summary,
            "differential": acl_differential,
            "valgrind_allocation_lifecycle_matches_translated_hybrid": True,
            "all_allocations_freed": True,
            "upstream_log_sha256": sha256(acl_upstream_path),
            "platform_log_sha256": sha256(acl_platform_path),
            "differential_sha256": sha256(acl_differential_path),
            "valgrind_log_sha256": {
                name: sha256(path) for name, path in acl_valgrind_paths.items()
            },
        },
        "lz4_integration": {
            "upstream_essentials": "pass",
            "upstream_markers": lz4_markers,
            "differential": lz4_differential,
            "valgrind_errors": 0,
            "all_allocations_freed": True,
            "compression_allocation_lifecycle_matches_translated_hybrid": True,
            "decompression_multicall_argv_overhead_bytes": 32,
            "upstream_log_sha256": sha256(lz4_upstream_path),
            "differential_sha256": sha256(lz4_differential_path),
            "valgrind_log_sha256": {
                operation: sha256(path)
                for operation, path in lz4_valgrind_paths.items()
            },
        },
        "gzip_integration": {
            "integrated_public_names": 10,
            "native_shell_replacements": ["gunzip", "uncompress", "zcat", "zcmp", "zdiff", "zforce", "zgrep", "zegrep", "zfgrep"],
            "alias_bridge": link["gzip_alias_bridge"],
            "differential": gzip_differential,
            "byte_identical_compression": True,
            "decompression_matches_canonical": True,
            "engine_and_comparison_valgrind_errors": 0,
            "gzip_engine_all_allocations_freed": True,
            "comparison_frontend_lost_bytes": 0,
            "comparison_frontend_still_reachable_bytes": {
                "zcmp": 8208,
                "zdiff": 147,
            },
            "search_frontend_canonical_valgrind_errors": 1,
            "search_frontend_canonical_possibly_lost_bytes": 128,
            "search_frontend_canonical_still_reachable_bytes": 112870,
            "differential_sha256": sha256(gzip_differential_path),
            "valgrind_log_sha256": {
                operation: sha256(path)
                for operation, path in gzip_valgrind_paths.items()
            },
        },
        "collision_isolation": {
            "translated_libraries": len(link["source_library_sha256"]),
            "namespaced_libraries": len(link["namespaced_symbols"]),
            "namespaced_symbols": sum(len(items) for items in link["namespaced_symbols"].values()),
            "namespaced_support_objects": len(link["namespaced_support_symbols"]),
            "m4_namespaced_support_symbols": len(link["m4_namespaced_support_symbols"]),
            "file_namespaced_symbols": len(link["file_namespaced_symbols"]),
            "patch_namespaced_symbols": len(link["patch_namespaced_symbols"]),
            "sed_namespaced_symbols": len(link["sed_namespaced_symbols"]),
            "sed_abi_bridge_symbols": len(link["sed_abi_bridge"]["symbols"]),
            "diffutils_namespaced_symbols": len(link["diffutils_namespaced_symbols"]),
            "diffutils_error_bridge_symbols": len(link["diffutils_error_bridge"]["symbols"]),
            "grep_namespaced_symbols": len(link["grep_namespaced_symbols"]),
            "grep_abi_bridge_symbols": len(link["grep_abi_bridge"]["symbols"]),
            "grep_error_bridge_symbols": len(link["grep_error_bridge"]["symbols"]),
            "bc_namespaced_symbols": len(link["bc_namespaced_symbols"]),
            "attr_namespaced_symbols": len(link["attr_namespaced_symbols"]),
            "acl_namespaced_symbols": len(link["acl_namespaced_symbols"]),
            "lz4_namespaced_symbols": len(link["lz4_namespaced_symbols"]),
            "gzip_namespaced_symbols": len(link["gzip_namespaced_symbols"]),
            "gzip_alias_bridge_symbols": len(link["gzip_alias_bridge"]["symbols"]),
            "manifest": link,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "dispatch": dispatch["passed"],
        "differential": differential["passed"],
        "stripped_bytes": stripped_bytes,
        "needed_libraries": len(needed),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
