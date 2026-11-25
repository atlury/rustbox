#!/usr/bin/env python3
"""Exercise Zstd's default lorem benchmark and its installed commands against both canonical compilers."""
# SPDX-License-Identifier: BSD-3-Clause OR GPL-2.0-only
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

from check_cargo_private_inlines import ROOT, digest

ORACLE = ROOT / "work/analysis/zstd-1.5.7/oracle"
DRIVER = ROOT / "tests/zstd-oracle-differential.py"


def benchmarks(executable):
    outcomes = {}
    for size, extra in ((65536, ["-B64K"]), (10000000, [])):
        run = subprocess.run([executable, "-b1", "-i0", *extra], env=dict(os.environ, LC_ALL="C"),
                             timeout=240, capture_output=True, check=True)
        rows = set(re.findall(rb'Lorem ipsum\s*:\s*(\d+)\s*->\s*(\d+)\s*\(x([\d.]+)\)', run.stdout + run.stderr))
        if len(rows) != 1:
            raise ValueError(f"incomplete Zstd benchmark for {size} bytes")
        observed, compressed, ratio = rows.pop()
        if int(observed) != size or not 0 < int(compressed) < size:
            raise ValueError("unexpected Zstd benchmark size")
        outcomes[str(size)] = dict(compressed_bytes=int(compressed), ratio=ratio.decode())
    return outcomes


def compare(directory, result_dir):
    candidates = benchmarks(directory / "zstd")
    pins = json.loads((ROOT / "evidence/zstd-1.5.7-oracle.json").read_bytes())["binaries"]
    suites = {}
    for cc in ("gcc", "clang"):
        canon = ORACLE / (cc + "-root/usr/bin")
        if digest(canon / "zstd") != pins[cc]["sha256"] or benchmarks(canon / "zstd") != candidates:
            raise ValueError(f"{cc} canonical Zstd executable or benchmark differs")
        path = result_dir / (cc + ".json")
        subprocess.run(["python3", DRIVER, "--gcc-directory", canon, "--clang-directory", directory,
                        "--output", path], check=True, stdout=subprocess.DEVNULL)
        result = json.loads(path.read_bytes())
        if result["cases"] != 17 or result["passed"] != 17:
            raise ValueError("incomplete Zstd command differential")
        suites[cc] = result["passed"]
    return dict(synthetic=candidates, command_cases=suites, command_driver_sha256=digest(DRIVER))


def archive_commands(link, pilot):
    row = json.loads((pilot / "pilot.json").read_bytes())
    release = json.loads(link.read_bytes())
    archive = pilot / Path(row["archive"]).name
    if (digest(archive) != row["candidate_sha256"] or row["control_sha256"] != release["source_library_sha256"][row["archive"]]
            or row["control_binary_sha256"] != release["binary"]["sha256"]):
        raise ValueError("candidate or selected parent archive changed")
    with TemporaryDirectory() as tmp:
        directory = Path(tmp)
        subprocess.run(["clang-18", "-O2", "-Wl,--gc-sections", ROOT / "bridges/zstd_main.c", archive,
                        "-ldl", "-lpthread", "-lm", "-lrt", "-lutil", "-o", directory / "zstd"], check=True)
        for name in ("unzstd", "zstdmt", "zstdcat"):
            (directory / name).symlink_to("zstd")
        for name in ("zstdgrep", "zstdless"):
            (directory / name).symlink_to(ORACLE / "gcc-root/usr/bin" / name)
        return dict(compare(directory, directory), candidate_sha256=digest(archive))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path)
    parser.add_argument("pilot", type=Path)
    args = parser.parse_args()
    print(json.dumps(archive_commands(args.link, args.pilot), indent=2, sort_keys=True))
