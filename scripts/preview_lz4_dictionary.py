#!/usr/bin/env python3
"""Compare four LZ4 frontends and the synthetic dictionary benchmark in the linked multicall."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

from check_cargo_private_inlines import ROOT, digest
from link_rustbox_multicall import namespace_lz4_library
from preview_cargo_multicall import preview


def synthetic(command):
    result = subprocess.run([*command, "-b1", "-i0"], capture_output=True, check=True, timeout=180,
                            env=dict(os.environ, LC_ALL="C"))
    log = result.stdout + result.stderr
    # Each progress line carries sizes and throughput. Timing depends on load.
    matches = set(re.findall(rb"Lorem ipsum\s*:\s*(\d+)\s*->\s*(\d+)\s+\(([\d.]+)\)", log))
    if len(matches) != 1 or b"1#" not in log or b"WARNING" in log:
        raise ValueError(f"incomplete LZ4 compression/decompression benchmark: {log[-320:]!r}")
    size, compressed, ratio = matches.pop()
    return dict(input_bytes=int(size), compressed_bytes=int(compressed), ratio=ratio.decode("ascii"))


def commands(elf, tmp):
    oracle = ROOT / "work/analysis/lz4-1.11.1/oracle"
    driver = ROOT / "tests/lz4-oracle-differential.py"
    names = ("lz4", "lz4c", "lz4cat", "unlz4")
    pins = json.loads((ROOT / "evidence/lz4-1.11.1-oracle.json").read_bytes())["binaries"]
    for cc in ("gcc", "clang"):
        if any(digest(oracle / cc / name) != pins[cc]["sha256"] for name in names):
            raise ValueError(f"unrecognized canonical {cc} LZ4 frontend")
    benchmark = {cc: synthetic([oracle / cc / "lz4"]) for cc in ("gcc", "clang")}
    cases = {}
    for mode in ("applet", "subcommand"):
        directory = tmp / mode
        directory.mkdir()
        for name in names:
            binary = directory / name
            if mode == "applet":
                binary.symlink_to(elf)
            else:
                binary.write_text("#!/bin/sh\nexec " + shlex.quote(str(elf)) + " " + name + ' "$@"\n')
                binary.chmod(0o755)
        benchmark[mode] = synthetic([directory / "lz4"])
        for cc in ("gcc", "clang"):
            report = directory / (cc + ".json")
            subprocess.run(["python3", driver, "--gcc-directory", oracle / cc, "--clang-directory", directory,
                            "--output", report], check=True, stdout=subprocess.DEVNULL)
            row = json.loads(report.read_bytes())
            if row["cases"] != row["passed"] or row["cases"] != 27:
                raise ValueError("incomplete LZ4 command comparison")
            cases[f"{mode}-{cc}"] = row["cases"]
    if (benchmark["gcc"]["input_bytes"] != 10_000_000 or
            any(v != benchmark["gcc"] for v in benchmark.values())):
        raise ValueError("LZ4 benchmark sizes or ratio differ from canonical results")
    return dict(canonical_cases=cases, synthetic_benchmark=benchmark, cli_driver_sha256=digest(driver))


def namespace(path, residues, release, stage):
    archive, symbols = namespace_lz4_library(path, stage)
    if residues or symbols != release["lz4_namespaced_symbols"]:
        raise ValueError("LZ4 symbol closure differs from the selected multicall")
    return archive, []


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("parent", "log", "pilot", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    qualified = json.loads((ROOT / "evidence/lz4-benchmark-dictionary-pilot.json").read_bytes())
    preview(args.parent, args.log, args.pilot, args.output, qualified, namespace, commands)
