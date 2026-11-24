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
    parser.add_argument("--less-report-directory", type=Path, required=True)
    parser.add_argument("--gzip-report-directory", type=Path, required=True)
    parser.add_argument("--xz-report-directory", type=Path, required=True)
    parser.add_argument("--zstd-report-directory", type=Path, required=True)
    parser.add_argument("--tar-report-directory", type=Path, required=True)
    parser.add_argument("--ncurses-report-directory", type=Path, required=True)
    parser.add_argument("--findutils-report-directory", type=Path, required=True)
    parser.add_argument("--gawk-report-directory", type=Path, required=True)
    parser.add_argument("--flex-report-directory", type=Path, required=True)
    parser.add_argument("--bison-report-directory", type=Path, required=True)
    parser.add_argument("--curl-report-directory", type=Path, required=True)
    parser.add_argument("--inetutils-report-directory", type=Path, required=True)
    parser.add_argument("--kmod-report-directory", type=Path, required=True)
    parser.add_argument("--procps-report-directory", type=Path, required=True)
    parser.add_argument("--shadow-report-directory", type=Path, required=True)
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
    less_directory = args.less_report_directory.resolve()
    gzip_directory = args.gzip_report_directory.resolve()
    xz_directory = args.xz_report_directory.resolve()
    zstd_directory = args.zstd_report_directory.resolve()
    tar_directory = args.tar_report_directory.resolve()
    ncurses_directory = args.ncurses_report_directory.resolve()
    findutils_directory = args.findutils_report_directory.resolve()
    gawk_directory = args.gawk_report_directory.resolve()
    flex_directory = args.flex_report_directory.resolve()
    bison_directory = args.bison_report_directory.resolve()
    curl_directory = args.curl_report_directory.resolve()
    inetutils_directory = args.inetutils_report_directory.resolve()
    kmod_directory = args.kmod_report_directory.resolve()
    procps_directory = args.procps_report_directory.resolve()
    shadow_directory = args.shadow_report_directory.resolve()
    m4_differential = json.loads((m4_directory / "differential.json").read_text())
    m4_language = (m4_directory / "language-check.log").read_text(errors="replace")
    m4_valgrind = (m4_directory / "valgrind.log").read_text(errors="replace")
    if dispatch["cases"] != 882 or dispatch["passed"] != 882 or dispatch["failures"]:
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
    less_differential_path = less_directory / "differential.json"
    less_differential = json.loads(less_differential_path.read_text())
    less_valgrind_paths = {
        applet: less_directory / f"valgrind-{applet}.log"
        for applet in ("less", "lessecho")
    }
    less_markers = {
        "less": [
            "ERROR SUMMARY: 0 errors", "definitely lost: 0 bytes",
            "indirectly lost: 0 bytes", "still reachable: 5,952 bytes in 22 blocks",
        ],
        "lessecho": [
            "ERROR SUMMARY: 0 errors",
            "All heap blocks were freed -- no leaks are possible",
        ],
    }
    for applet, path in less_valgrind_paths.items():
        text = path.read_text(errors="replace")
        if any(marker not in text for marker in less_markers[applet]):
            raise RuntimeError(f"unified Less {applet} Valgrind comparison is incomplete")
    if less_differential.get("cases") != 22 or less_differential.get("passed") != 22:
        raise RuntimeError("unified Less integration comparison is incomplete")
    gzip_differential_path = gzip_directory / "differential.json"
    gzip_differential = json.loads(gzip_differential_path.read_text())
    gzip_valgrind_paths = {
        operation: gzip_directory / f"valgrind-{operation}.log"
        for operation in ("compress", "decompress", "zcmp", "zdiff", "zgrep", "zless", "zmore", "znew", "gzexe")
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
        elif operation in {"compress", "decompress", "zless", "zmore", "znew", "gzexe"}:
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
    if gzip_differential.get("cases") != 108 or gzip_differential.get("passed") != 108:
        raise RuntimeError("unified GNU Gzip integration comparison is incomplete")
    xz_differential_path = xz_directory / "differential.json"
    xz_differential = json.loads(xz_differential_path.read_text())
    xz_upstream_path = xz_directory / "upstream-scripts.log"
    xz_upstream = xz_upstream_path.read_text(errors="replace")
    xz_valgrind_paths = {
        operation: xz_directory / f"valgrind-{operation}.log"
        for operation in ("compress", "decompress")
    }
    for operation, path in xz_valgrind_paths.items():
        text = path.read_text(errors="replace")
        required = [
            "ERROR SUMMARY: 0 errors",
            "definitely lost: 0 bytes in 0 blocks",
            "indirectly lost: 0 bytes in 0 blocks",
            "possibly lost: 0 bytes in 0 blocks",
        ]
        if any(marker not in text for marker in required):
            raise RuntimeError(f"unified XZ {operation} Valgrind comparison is incomplete")
    if (
        xz_differential.get("cases") != 70
        or xz_differential.get("passed") != 70
        or "test_scripts.sh: PASS" not in xz_upstream
    ):
        raise RuntimeError("unified XZ integration comparison is incomplete")
    zstd_differential_path = zstd_directory / "differential.json"
    zstd_differential = json.loads(zstd_differential_path.read_text())
    zstd_valgrind_paths = {
        operation: zstd_directory / f"valgrind-{operation}.log"
        for operation in ("compress", "decompress")
    }
    for operation, path in zstd_valgrind_paths.items():
        text = path.read_text(errors="replace")
        required = ["ERROR SUMMARY: 0 errors", "All heap blocks were freed -- no leaks are possible"]
        if any(marker not in text for marker in required):
            raise RuntimeError(f"unified zstd {operation} Valgrind comparison is incomplete")
    if zstd_differential.get("cases") != 17 or zstd_differential.get("passed") != 17:
        raise RuntimeError("unified zstd integration comparison is incomplete")
    tar_differential_path = tar_directory / "differential.json"
    tar_differential = json.loads(tar_differential_path.read_text())
    tar_valgrind_paths = {
        operation: tar_directory / f"valgrind-{operation}.log"
        for operation in ("create", "list", "extract", "rmt")
    }
    for operation, path in tar_valgrind_paths.items():
        text = path.read_text(errors="replace")
        required = [
            "ERROR SUMMARY: 0 errors",
            "definitely lost: 0 bytes in 0 blocks",
            "indirectly lost: 0 bytes in 0 blocks",
            "possibly lost: 0 bytes in 0 blocks",
        ]
        if any(marker not in text for marker in required):
            raise RuntimeError(f"unified GNU tar {operation} Valgrind comparison is incomplete")
    if tar_differential.get("cases") != 18 or tar_differential.get("passed") != 18:
        raise RuntimeError("unified GNU tar integration comparison is incomplete")
    ncurses_differential_path = ncurses_directory / "differential.json"
    ncurses_differential = json.loads(ncurses_differential_path.read_text())
    ncurses_names = [
        "captoinfo", "clear", "infocmp", "infotocap", "reset", "tabs",
        "tic", "toe", "tput", "tset",
    ]
    ncurses_valgrind_paths = {
        name: ncurses_directory / f"valgrind-{name}.log"
        for name in ncurses_names
    }
    for name, path in ncurses_valgrind_paths.items():
        text = path.read_text(errors="replace")
        required = ["ERROR SUMMARY: 0 errors"]
        if any(marker not in text for marker in required) or not (
            "All heap blocks were freed" in text
            or (
                "definitely lost: 0 bytes" in text
                and "indirectly lost: 0 bytes" in text
                and "possibly lost: 0 bytes" in text
            )
        ):
            raise RuntimeError(f"unified Ncurses {name} Valgrind comparison is incomplete")
    if (
        ncurses_differential.get("cases") != 27
        or ncurses_differential.get("passed") != 27
    ):
        raise RuntimeError("unified Ncurses integration comparison is incomplete")
    findutils_differential_path = findutils_directory / "differential.json"
    findutils_differential = json.loads(findutils_differential_path.read_text())
    findutils_valgrind_paths = {
        name: findutils_directory / f"valgrind-{name}.log"
        for name in ("find", "xargs", "locate", "updatedb")
    }
    if (
        findutils_differential.get("cases") != 38
        or findutils_differential.get("passed") != 38
    ):
        raise RuntimeError("unified Findutils differential is incomplete")
    for name, path in findutils_valgrind_paths.items():
        if "ERROR SUMMARY: 0 errors" not in path.read_text(errors="replace"):
            raise RuntimeError(f"unified Findutils {name} Valgrind result is incomplete")
    gawk_differential_path = gawk_directory / "differential.json"
    gawk_differential = json.loads(gawk_differential_path.read_text())
    gawkbug_differential_path = gawk_directory / "gawkbug-differential.json"
    gawkbug_differential = json.loads(gawkbug_differential_path.read_text())
    gawk_upstream_path = gawk_directory / "upstream-tests.log"
    gawk_upstream = gawk_upstream_path.read_text(errors="replace")
    if (
        gawk_differential.get("cases") != 26
        or gawk_differential.get("passed") != 26
        or gawkbug_differential.get("cases") != 6
        or gawkbug_differential.get("passed") != 6
        or len(re.findall(r"Segmentation fault.*GAWK_PERSIST_FILE=test\.pma", gawk_upstream)) != 1
        or len(re.findall(r"Error 139", gawk_upstream)) != 1
    ):
        raise RuntimeError("unified GNU Gawk integration comparison is incomplete")
    gawk_valgrind_paths = {
        name: gawk_directory / f"valgrind-{name}.log"
        for name in ("gawk", "awk", "gawkbug")
    }
    for name, path in gawk_valgrind_paths.items():
        text = path.read_text(errors="replace")
        zero_loss = all(marker in text for marker in (
            "definitely lost: 0 bytes", "indirectly lost: 0 bytes",
            "possibly lost: 0 bytes",
        ))
        if "ERROR SUMMARY: 0 errors" not in text or not (
            "All heap blocks were freed" in text or zero_loss
        ):
            raise RuntimeError(f"unified GNU Gawk {name} Valgrind result is incomplete")
    flex_differential_path = flex_directory / "differential.json"
    flex_differential = json.loads(flex_differential_path.read_text())
    flex_frontends_path = flex_directory / "frontends.json"
    flex_frontends = json.loads(flex_frontends_path.read_text())
    flex_upstream_path = flex_directory / "upstream-tests.log"
    flex_upstream = flex_upstream_path.read_text(errors="replace")
    if (
        flex_differential.get("cases") != 14
        or flex_differential.get("passed") != 14
        or flex_frontends.get("cases") != 3
        or flex_frontends.get("passed") != 3
        or "# TOTAL: 114" not in flex_upstream
        or "# PASS:  114" not in flex_upstream
        or re.search(r"^# (?:FAIL|XPASS|ERROR):\s+[1-9]", flex_upstream, re.MULTILINE)
    ):
        raise RuntimeError("unified Flex integration comparison is incomplete")
    flex_valgrind_paths = {
        name: flex_directory / f"valgrind-{name}.log"
        for name in ("flex-version", "flex++-version", "lex-version", "flex-invalid")
    }
    for name, path in flex_valgrind_paths.items():
        text = path.read_text(errors="replace")
        if "ERROR SUMMARY: 0 errors" not in text or not all(
            marker in text for marker in (
                "definitely lost: 0 bytes", "indirectly lost: 0 bytes",
                "possibly lost: 0 bytes",
            )
        ):
            raise RuntimeError(f"unified Flex {name} Valgrind result is incomplete")
    bison_differential_path = bison_directory / "differential.json"
    bison_differential = json.loads(bison_differential_path.read_text())
    bison_yacc_path = bison_directory / "yacc-frontend.json"
    bison_yacc = json.loads(bison_yacc_path.read_text())
    bison_upstream_path = bison_directory / "upstream-tests.log"
    bison_upstream = bison_upstream_path.read_text(errors="replace")
    bison_targeted_path = bison_directory / "upstream-tests-targeted.log"
    bison_targeted = bison_targeted_path.read_text(errors="replace")
    bison_valgrind_path = bison_directory / "valgrind-help.log"
    bison_valgrind = bison_valgrind_path.read_text(errors="replace")
    bison_failed = set(re.findall(
        r"^\s*(\d+): .*FAILED", bison_upstream, re.MULTILINE
    ))
    if (
        bison_differential.get("cases") != 12
        or bison_differential.get("passed") != 12
        or bison_differential.get("compiled_parsers") != 5
        or bison_differential.get("right_embedded") is not True
        or bison_yacc.get("passed") is not True
        or bison_yacc.get("hybrid_embedded") is not True
        or len(bison_failed) != 57
        or "2" not in bison_failed
        or "1 test was successful" not in bison_targeted
        or "FAILED" in bison_targeted
        or "ERROR SUMMARY: 0 errors" not in bison_valgrind
    ):
        raise RuntimeError("unified Bison integration comparison is incomplete")
    curl_differential_path = curl_directory / "differential.json"
    curl_differential = json.loads(curl_differential_path.read_text())
    curl_config_path = curl_directory / "curl-config-differential.json"
    curl_config = json.loads(curl_config_path.read_text())
    curl_valgrind_paths = {
        operation: curl_directory / f"valgrind-{operation}.log"
        for operation in ("version", "file")
    }
    for operation, path in curl_valgrind_paths.items():
        text = path.read_text(errors="replace")
        zero_loss = all(marker in text for marker in (
            "definitely lost: 0 bytes", "indirectly lost: 0 bytes",
            "possibly lost: 0 bytes",
        ))
        if "ERROR SUMMARY: 0 errors" not in text or not (
            "All heap blocks were freed" in text or zero_loss
        ):
            raise RuntimeError(
                f"unified curl {operation} Valgrind result is incomplete"
            )
    if (
        curl_differential.get("cases") != 12
        or curl_differential.get("passed") != 12
        or curl_differential.get("gcc_clang_exact") is not True
        or curl_config.get("cases") != 24
        or curl_config.get("passed") != 24
        or curl_config.get("canonical_native_exact") is not True
        or link.get("curl_public_names") != 2
        or link.get("total_dispatch_names") != 445
    ):
        raise RuntimeError("unified curl integration comparison is incomplete")
    inetutils_differential_path = inetutils_directory / "differential.json"
    inetutils_differential = json.loads(inetutils_differential_path.read_text())
    inetutils_names = sorted(link.get("inetutils_namespaced_symbols", {}))
    inetutils_valgrind_paths = {
        name: inetutils_directory / f"valgrind-{name}.log"
        for name in inetutils_names
    }
    for name, path in inetutils_valgrind_paths.items():
        text = path.read_text(errors="replace")
        zero_loss = all(marker in text for marker in (
            "definitely lost: 0 bytes", "indirectly lost: 0 bytes",
            "possibly lost: 0 bytes",
        ))
        if "ERROR SUMMARY: 0 errors" not in text or not (
            "All heap blocks were freed" in text or zero_loss
        ):
            raise RuntimeError(
                f"unified Inetutils {name} Valgrind result is incomplete"
            )
    if (
        inetutils_differential.get("applets") != 26
        or inetutils_differential.get("cases") != 133
        or inetutils_differential.get("passed") != 133
        or len(inetutils_names) != 26
        or link.get("inetutils_programs") != 26
    ):
        raise RuntimeError("unified Inetutils integration comparison is incomplete")
    kmod_differential_path = kmod_directory / "differential.json"
    kmod_differential = json.loads(kmod_differential_path.read_text())
    kmod_programs = ("kmod", "depmod", "insmod", "lsmod", "modinfo", "modprobe", "rmmod")
    kmod_valgrind_paths = {
        name: kmod_directory / f"valgrind-{name}.log" for name in kmod_programs
    }
    for name, path in kmod_valgrind_paths.items():
        text = path.read_text(errors="replace")
        zero_loss = all(marker in text for marker in (
            "definitely lost: 0 bytes", "indirectly lost: 0 bytes",
            "possibly lost: 0 bytes",
        ))
        if "ERROR SUMMARY: 0 errors" not in text or not (
            "All heap blocks were freed" in text or zero_loss
        ):
            raise RuntimeError(f"unified Kmod {name} Valgrind result is incomplete")
    if (
        kmod_differential.get("applets") != 7
        or kmod_differential.get("cases") != 25
        or kmod_differential.get("passed") != 25
        or not all(record.get("passed") for record in kmod_differential.get("records", []))
        or link.get("kmod_programs") != 7
        or not link.get("kmod_namespaced_symbols")
    ):
        raise RuntimeError("unified Kmod integration comparison is incomplete")
    procps_differential_path = procps_directory / "differential.json"
    procps_differential = json.loads(procps_differential_path.read_text())
    procps_programs = (
        "free", "hugetop", "procps-kill", "pgrep", "pidof", "pidwait", "pkill",
        "pmap", "ps", "pwdx", "skill", "slabtop", "snice", "sysctl",
        "tload", "top", "procps-uptime", "vmstat", "w", "watch",
    )
    procps_valgrind_paths = {
        name: procps_directory / f"valgrind-{name}.log" for name in procps_programs
    }
    for name, path in procps_valgrind_paths.items():
        text = path.read_text(errors="replace")
        if name == "sysctl":
            if (
                "definitely lost: 16 bytes in 1 blocks" not in text
                or "ERROR SUMMARY: 1 errors" not in text
            ):
                raise RuntimeError("unified Procps sysctl baseline changed")
            continue
        zero_loss = all(marker in text for marker in (
            "definitely lost: 0 bytes", "indirectly lost: 0 bytes",
            "possibly lost: 0 bytes",
        ))
        if "ERROR SUMMARY: 0 errors" not in text or not (
            "All heap blocks were freed" in text or zero_loss
        ):
            raise RuntimeError(f"unified Procps {name} Valgrind result is incomplete")
    if (
        procps_differential.get("programs") != 20
        or procps_differential.get("cases") != 51
        or procps_differential.get("passed") != 51
        or not all(record.get("passed") for record in procps_differential.get("records", []))
        or link.get("procps_programs") != 20
        or not link.get("procps_namespaced_symbols")
    ):
        raise RuntimeError("unified Procps integration comparison is incomplete")
    shadow_differential_path = shadow_directory / "differential.json"
    shadow_differential = json.loads(shadow_differential_path.read_text())
    shadow_programs = (
        "chage", "chfn", "chgpasswd", "chpasswd", "chsh", "faillog",
        "getsubids", "gpasswd", "groupadd", "groupdel", "groupmod", "grpck",
        "grpconv", "grpunconv", "lastlog", "login", "newgidmap", "newgrp",
        "newuidmap", "newusers", "nologin", "passwd", "pwck", "pwconv",
        "pwunconv", "su", "useradd", "userdel", "usermod", "vipw", "sg",
        "vigr",
    )
    shadow_valgrind_paths = {
        name: shadow_directory / f"valgrind-{name}.log" for name in shadow_programs
    }
    for name, path in shadow_valgrind_paths.items():
        text = path.read_text(errors="replace")
        if name == "gpasswd":
            if (
                "definitely lost: 48 bytes in 1 blocks" not in text
                or "indirectly lost: 28 bytes in 5 blocks" not in text
                or "ERROR SUMMARY: 6 errors" not in text
            ):
                raise RuntimeError("unified Shadow gpasswd baseline changed")
            continue
        if "ERROR SUMMARY: 0 errors" not in text:
            raise RuntimeError(f"unified Shadow {name} Valgrind result is incomplete")
    if (
        shadow_differential.get("programs") != 32
        or shadow_differential.get("cases") != 79
        or shadow_differential.get("stateful_cases") != 8
        or shadow_differential.get("passed") != 79
        or not all(record.get("passed") for record in shadow_differential.get("records", []))
        or link.get("shadow_programs") != 32
        or len(link.get("shadow_namespaced_symbols", [])) != 265
        or len(link.get("shadow_coalesced_runtime_members", [])) != 211
    ):
        raise RuntimeError("unified Shadow integration comparison is incomplete")
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
    forbidden = [
        name for name in needed
        if "selinux" in name or "systemd" in name or name.startswith("libacl.so")
    ]
    undefined = subprocess.run(
        ["nm", "-u", str(binary)], check=True, text=True, stdout=subprocess.PIPE
    ).stdout
    forbidden_undefined = sorted(
        line.strip() for line in undefined.splitlines()
        if "selinux" in line.lower() or "systemd" in line.lower()
    )
    if forbidden or forbidden_undefined:
        raise RuntimeError("unified binary retains a forbidden security-library dependency")
    evidence_link = dict(link)
    curl_symbol_bytes = json.dumps(
        link["curl_namespaced_symbols"], separators=(",", ":"), sort_keys=True
    ).encode()
    evidence_link["curl_namespaced_symbols"] = {
        "count": len(link["curl_namespaced_symbols"]),
        "sha256": hashlib.sha256(curl_symbol_bytes).hexdigest(),
    }
    inetutils_symbol_bytes = json.dumps(
        link["inetutils_namespaced_symbols"], separators=(",", ":"), sort_keys=True
    ).encode()
    evidence_link["inetutils_namespaced_symbols"] = {
        "programs": len(link["inetutils_namespaced_symbols"]),
        "count": sum(len(items) for items in link["inetutils_namespaced_symbols"].values()),
        "sha256": hashlib.sha256(inetutils_symbol_bytes).hexdigest(),
    }
    kmod_symbol_bytes = json.dumps(
        link["kmod_namespaced_symbols"], separators=(",", ":"), sort_keys=True
    ).encode()
    evidence_link["kmod_namespaced_symbols"] = {
        "count": len(link["kmod_namespaced_symbols"]),
        "sha256": hashlib.sha256(kmod_symbol_bytes).hexdigest(),
    }
    procps_symbol_bytes = json.dumps(
        link["procps_namespaced_symbols"], separators=(",", ":"), sort_keys=True
    ).encode()
    evidence_link["procps_namespaced_symbols"] = {
        "count": len(link["procps_namespaced_symbols"]),
        "sha256": hashlib.sha256(procps_symbol_bytes).hexdigest(),
    }
    shadow_symbol_bytes = json.dumps(
        link["shadow_namespaced_symbols"], separators=(",", ":"), sort_keys=True
    ).encode()
    evidence_link["shadow_namespaced_symbols"] = {
        "count": len(link["shadow_namespaced_symbols"]),
        "sha256": hashlib.sha256(shadow_symbol_bytes).hexdigest(),
    }
    shadow_runtime_bytes = json.dumps(
        link["shadow_coalesced_runtime_members"],
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    evidence_link["shadow_coalesced_runtime_members"] = {
        "count": len(link["shadow_coalesced_runtime_members"]),
        "sha256": hashlib.sha256(shadow_runtime_bytes).hexdigest(),
    }
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-24",
        "status": "Coreutils, util-linux, GNU M4, pkgconf, File, GNU patch, GNU sed, GNU Diffutils, GNU Grep, GNU bc, GNU dc, attr, acl, LZ4, Less, GNU Gzip, XZ Utils, zstd, GNU tar, Ncurses, GNU Findutils, GNU Gawk, Flex, Bison, curl, GNU Inetutils, Kmod, Procps-ng, and Shadow integrated at canonical parity",
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
            "less": 2,
            "gzip_integrated_names": 14,
            "xz_integrated_names": 23,
            "zstd_integrated_names": 6,
            "tar_integrated_names": 2,
            "ncurses_integrated_names": 10,
            "findutils_integrated_names": 4,
            "gawk_integrated_names": 3,
            "flex_integrated_names": 3,
            "bison_integrated_names": 2,
            "curl_integrated_names": 2,
            "inetutils_integrated_names": 26,
            "kmod_integrated_names": 7,
            "procps_integrated_names": 20,
            "shadow_integrated_names": 32,
            "dispatch_names": 445,
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
        "gawk_integration": {
            "integrated_public_names": 3,
            "differential": gawk_differential,
            "gawkbug_stateful_differential": gawkbug_differential,
            "complete_upstream_suite": True,
            "pma_virtualization_failure_matches_canonical": True,
            "valgrind_errors": 0,
            "definitely_lost_bytes": 0,
            "indirectly_lost_bytes": 0,
            "possibly_lost_bytes": 0,
            "differential_sha256": sha256(gawk_differential_path),
            "gawkbug_differential_sha256": sha256(gawkbug_differential_path),
            "upstream_log_sha256": sha256(gawk_upstream_path),
            "valgrind_log_sha256": {
                name: sha256(path) for name, path in gawk_valgrind_paths.items()
            },
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
        "less_integration": {
            "differential": less_differential,
            "valgrind_errors": 0,
            "less_lost_bytes": 0,
            "less_still_reachable_bytes": 5952,
            "lessecho_all_allocations_freed": True,
            "differential_sha256": sha256(less_differential_path),
            "valgrind_log_sha256": {
                applet: sha256(path)
                for applet, path in less_valgrind_paths.items()
            },
        },
        "gzip_integration": {
            "integrated_public_names": 14,
            "native_shell_replacements": ["gunzip", "uncompress", "zcat", "zcmp", "zdiff", "zforce", "zgrep", "zegrep", "zfgrep", "zless", "zmore", "znew", "gzexe"],
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
            "less_frontend_all_allocations_freed": True,
            "pager_frontend_all_allocations_freed": True,
            "recompression_frontend_all_allocations_freed": True,
            "executable_frontend_all_allocations_freed": True,
            "executable_frontend_round_trip": True,
            "executable_launcher_bytes": 932,
            "differential_sha256": sha256(gzip_differential_path),
            "valgrind_log_sha256": {
                operation: sha256(path)
                for operation, path in gzip_valgrind_paths.items()
            },
        },
        "xz_integration": {
            "integrated_public_names": 23,
            "native_shell_replacements": [
                "xzdiff", "xzcmp", "xzegrep", "xzfgrep", "xzgrep", "xzless",
                "xzmore", "lzdiff", "lzcmp", "lzgrep", "lzegrep", "lzfgrep",
                "lzmore", "lzless",
            ],
            "alias_bridge": link["xz_alias_bridge"],
            "upstream_script_suite": "pass",
            "differential": xz_differential,
            "byte_identical_xz_compression": True,
            "decompression_matches_canonical": True,
            "engine_valgrind_errors": 0,
            "definitely_lost_bytes": 0,
            "indirectly_lost_bytes": 0,
            "possibly_lost_bytes": 0,
            "differential_sha256": sha256(xz_differential_path),
            "upstream_script_log_sha256": sha256(xz_upstream_path),
            "valgrind_log_sha256": {
                operation: sha256(path)
                for operation, path in xz_valgrind_paths.items()
            },
        },
        "zstd_integration": {
            "integrated_public_names": 6,
            "native_shell_replacements": ["zstdgrep", "zstdless"],
            "alias_bridge": link["zstd_alias_bridge"],
            "differential": zstd_differential,
            "byte_identical_compression": True,
            "decompression_matches_canonical": True,
            "engine_valgrind_errors": 0,
            "definitely_lost_bytes": 0,
            "indirectly_lost_bytes": 0,
            "possibly_lost_bytes": 0,
            "differential_sha256": sha256(zstd_differential_path),
            "valgrind_log_sha256": {
                operation: sha256(path)
                for operation, path in zstd_valgrind_paths.items()
            },
        },
        "tar_integration": {
            "integrated_public_names": 2,
            "canonical_c_abi_residue_units": 4,
            "translated_acl_imports": link["tar_acl_imports"],
            "coreutils_translated_acl_imports": link["coreutils_acl_imports"],
            "system_libacl_dependency": False,
            "differential": tar_differential,
            "byte_identical_deterministic_archive": True,
            "extracted_tree_matches_canonical": True,
            "valgrind_errors": 0,
            "definitely_lost_bytes": 0,
            "indirectly_lost_bytes": 0,
            "possibly_lost_bytes": 0,
            "differential_sha256": sha256(tar_differential_path),
            "valgrind_log_sha256": {
                operation: sha256(path)
                for operation, path in tar_valgrind_paths.items()
            },
        },
        "ncurses_integration": {
            "integrated_public_names": 10,
            "retained_entrypoints": 7,
            "canonical_c_abi_residue_units": 0,
            "external_ncurses_library_required_by_translated_applets": False,
            "differential": ncurses_differential,
            "valgrind_errors": 0,
            "definitely_lost_bytes": 0,
            "indirectly_lost_bytes": 0,
            "possibly_lost_bytes": 0,
            "differential_sha256": sha256(ncurses_differential_path),
            "valgrind_log_sha256": {
                name: sha256(path)
                for name, path in ncurses_valgrind_paths.items()
            },
        },
        "findutils_integration": {
            "integrated_public_names": 4,
            "translated_entrypoints": ["find", "frcode", "locate", "xargs"],
            "canonical_c_abi_residue_units": 3,
            "updatedb_external_script": False,
            "updatedb_pipeline": ["translated find", "translated GNU sort", "translated frcode"],
            "differential": findutils_differential,
            "valgrind_errors": 0,
            "differential_sha256": sha256(findutils_differential_path),
            "valgrind_log_sha256": {
                name: sha256(path)
                for name, path in findutils_valgrind_paths.items()
            },
        },
        "flex_integration": {
            "integrated_public_names": 3,
            "translated_entrypoint": "rustbox_flex_main",
            "native_frontends": ["flex++", "lex"],
            "upstream_tests": 114,
            "differential": flex_differential,
            "frontends": flex_frontends,
            "valgrind_errors": 0,
            "definitely_lost_bytes": 0,
            "indirectly_lost_bytes": 0,
            "possibly_lost_bytes": 0,
            "upstream_log_sha256": sha256(flex_upstream_path),
            "differential_sha256": sha256(flex_differential_path),
            "frontends_sha256": sha256(flex_frontends_path),
            "valgrind_log_sha256": {
                name: sha256(path) for name, path in flex_valgrind_paths.items()
            },
        },
        "bison_integration": {
            "integrated_public_names": 2,
            "translated_entrypoint": "rustbox_bison_engine_main",
            "native_frontend": "yacc",
            "embedded_resources": 22,
            "embedded_m4_dispatch": True,
            "external_bison_datadir_required": False,
            "differential": bison_differential,
            "yacc": bison_yacc,
            "full_upstream_inventory_groups": 776,
            "final_in_scope_passes": 707,
            "environmental_skips": 13,
            "excluded_java_d_groups": 56,
            "targeted_diagnostic_recheck": "pass",
            "valgrind_errors": 0,
            "upstream_log_sha256": sha256(bison_upstream_path),
            "targeted_log_sha256": sha256(bison_targeted_path),
            "differential_sha256": sha256(bison_differential_path),
            "yacc_sha256": sha256(bison_yacc_path),
            "valgrind_log_sha256": sha256(bison_valgrind_path),
        },
        "curl_integration": {
            "integrated_public_names": 2,
            "translated_entrypoint": "rustbox_curl_main",
            "native_frontend": "curl-config",
            "canonical_c_abi_residue_units": 1,
            "stable_translated_sources": 239,
            "differential": curl_differential,
            "curl_config": curl_config,
            "valgrind_errors": 0,
            "definitely_lost_bytes": 0,
            "indirectly_lost_bytes": 0,
            "possibly_lost_bytes": 0,
            "differential_sha256": sha256(curl_differential_path),
            "curl_config_sha256": sha256(curl_config_path),
            "valgrind_log_sha256": {
                operation: sha256(path)
                for operation, path in curl_valgrind_paths.items()
            },
        },
        "inetutils_integration": {
            "integrated_programs": 26,
            "stable_translated_sources": 287,
            "canonical_c_abi_residue_units": 1,
            "differential": inetutils_differential,
            "dispatch_aliases": {
                "hostname": "inetutils-hostname",
                "logger": "inetutils-logger",
            },
            "valgrind_programs": len(inetutils_valgrind_paths),
            "valgrind_errors": 0,
            "definitely_lost_bytes": 0,
            "indirectly_lost_bytes": 0,
            "possibly_lost_bytes": 0,
            "differential_sha256": sha256(inetutils_differential_path),
            "valgrind_log_sha256": {
                name: sha256(path) for name, path in inetutils_valgrind_paths.items()
            },
        },
        "kmod_integration": {
            "integrated_programs": 7,
            "stable_translated_sources": 26,
            "canonical_c_abi_residue_units": 0,
            "differential": kmod_differential,
            "valgrind_programs": len(kmod_valgrind_paths),
            "valgrind_errors": 0,
            "definitely_lost_bytes": 0,
            "indirectly_lost_bytes": 0,
            "possibly_lost_bytes": 0,
            "differential_sha256": sha256(kmod_differential_path),
            "valgrind_log_sha256": {
                name: sha256(path) for name, path in kmod_valgrind_paths.items()
            },
        },
        "procps_integration": {
            "integrated_programs": 20,
            "translated_engines": 17,
            "translated_sources": 49,
            "canonical_c_abi_residue_units": 0,
            "differential": procps_differential,
            "dispatch_aliases": {
                "kill": "procps-kill",
                "uptime": "procps-uptime",
            },
            "valgrind_programs": len(procps_valgrind_paths),
            "canonical_sysctl_definitely_lost_bytes": 16,
            "canonical_sysctl_valgrind_errors": 1,
            "other_valgrind_errors": 0,
            "differential_sha256": sha256(procps_differential_path),
            "valgrind_log_sha256": {
                name: sha256(path) for name, path in procps_valgrind_paths.items()
            },
        },
        "shadow_integration": {
            "integrated_programs": 32,
            "translated_engines": 30,
            "translated_sources": 196,
            "canonical_c_abi_residue_units": 0,
            "differential": shadow_differential,
            "dispatch_aliases": {
                name: f"shadow-{name}"
                for name in ("chfn", "chsh", "login", "newgrp", "nologin", "su", "vigr", "vipw")
            },
            "valgrind_programs": len(shadow_valgrind_paths),
            "canonical_gpasswd_definitely_lost_bytes": 48,
            "canonical_gpasswd_indirectly_lost_bytes": 28,
            "canonical_gpasswd_valgrind_errors": 6,
            "other_valgrind_errors": 0,
            "differential_sha256": sha256(shadow_differential_path),
            "valgrind_log_sha256": {
                name: sha256(path) for name, path in shadow_valgrind_paths.items()
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
            "gawk_namespaced_symbols": len(link["gawk_namespaced_symbols"]),
            "gawkbug_bridge_symbols": len(link["gawkbug_bridge"]["symbols"]),
            "grep_abi_bridge_symbols": len(link["grep_abi_bridge"]["symbols"]),
            "grep_error_bridge_symbols": len(link["grep_error_bridge"]["symbols"]),
            "bc_namespaced_symbols": len(link["bc_namespaced_symbols"]),
            "attr_namespaced_symbols": len(link["attr_namespaced_symbols"]),
            "acl_namespaced_symbols": len(link["acl_namespaced_symbols"]),
            "lz4_namespaced_symbols": len(link["lz4_namespaced_symbols"]),
            "less_namespaced_symbols": len(link["less_namespaced_symbols"]),
            "gzip_namespaced_symbols": len(link["gzip_namespaced_symbols"]),
            "gzip_alias_bridge_symbols": len(link["gzip_alias_bridge"]["symbols"]),
            "xz_namespaced_symbols": len(link["xz_namespaced_symbols"]),
            "xz_alias_bridge_symbols": len(link["xz_alias_bridge"]["symbols"]),
            "zstd_namespaced_symbols": len(link["zstd_namespaced_symbols"]),
            "zstd_alias_bridge_symbols": len(link["zstd_alias_bridge"]["symbols"]),
            "tar_namespaced_symbols": len(link["tar_namespaced_symbols"]),
            "ncurses_namespaced_symbols": len(link["ncurses_namespaced_symbols"]),
            "findutils_namespaced_symbols": len(link["findutils_namespaced_symbols"]),
            "flex_namespaced_symbols": len(link["flex_namespaced_symbols"]),
            "bison_namespaced_symbols": len(link["bison_namespaced_symbols"]),
            "curl_namespaced_symbols": len(link["curl_namespaced_symbols"]),
            "inetutils_namespaced_symbols": sum(
                len(items) for items in link["inetutils_namespaced_symbols"].values()
            ),
            "kmod_namespaced_symbols": len(link["kmod_namespaced_symbols"]),
            "procps_namespaced_symbols": len(link["procps_namespaced_symbols"]),
            "shadow_namespaced_symbols": len(link["shadow_namespaced_symbols"]),
            "shadow_coalesced_runtime_members": len(
                link["shadow_coalesced_runtime_members"]
            ),
            "curl_config_bridge_symbols": len(
                link["curl_config_frontend_bridge"]["symbols"]
            ),
            "tar_acl_imports": len(link["tar_acl_imports"]),
            "coreutils_acl_imports": len(link["coreutils_acl_imports"]),
            "manifest": evidence_link,
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
