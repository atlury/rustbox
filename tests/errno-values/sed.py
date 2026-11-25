#!/usr/bin/env python3
"""Compare GNU sed's errno-sensitive quoting, allocation and command behavior on selected archives."""
# SPDX-License-Identifier: 0BSD
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from check_cargo_private_inlines import digest


def run(link, pilot, work):
    release = json.loads(link.read_bytes())
    pins = json.loads((ROOT / "evidence/sed-4.10-oracle.json").read_bytes())["binaries"]
    key, = [k for k in release["source_library_sha256"] if k.endswith("/libsed_4_10_normalized_audit.a")]
    archives = {"parent": ROOT / key}
    if digest(archives["parent"]) != release["source_library_sha256"][key]:
        raise ValueError("GNU sed release archive differs")
    if pilot:
        record = json.loads((pilot / "pilot.json").read_bytes())
        archives["candidate"] = pilot / Path(key).name
        if (record["archive"] != key or record["control_sha256"] != digest(archives["parent"])
                or record["control_binary_sha256"] != release["binary"]["sha256"]
                or record["candidate_sha256"] != digest(archives["candidate"])):
            raise ValueError("GNU sed candidate differs")
    oracle = ROOT / "work/analysis/sed-4.10/oracle"
    cli = {}
    for cc in ("gcc", "clang"):
        build = Path("/rustbox-sed") / ("oracle-" + cc)
        binary = oracle / ("sed-" + cc)
        if digest(binary) != pins[cc]["sha256"] or digest(build / "sed/sed") != digest(binary):
            raise ValueError("unexpected canonical sed")
        cli[cc] = binary
        archives[cc] = build / "lib/libsed.a"
    driver = Path(__file__).with_name("sed-gnulib.c")
    flags = ["-lacl", "-lattr", "-ldl", "-lpthread", "-lm"]
    observations = {}
    env = dict(os.environ, LC_ALL="C", TZ="UTC")
    for name, archive in archives.items():
        exe = work / ("api-" + name)
        support = [] if name in ("gcc", "clang") else [ROOT / "bridges/sed_abi.c"]
        subprocess.run(["clang-18", "-O2", "-Wl,--gc-sections", driver, *support, archive, *flags, "-o", exe], check=True)
        args = [exe]
        for checked in (False, True):
            if checked:
                log = work / "valgrind.log"
                args = ["valgrind", "--error-exitcode=99", "--leak-check=full", "--log-file=" + str(log), exe]
            result = subprocess.run(args, check=True, env=env, capture_output=True, timeout=180)
            if result.stderr or (checked and "ERROR SUMMARY: 0 errors" not in log.read_text()):
                raise ValueError((name, result.stderr))
            observations[name + ("-memcheck" if checked else "")] = sha256(result.stdout).hexdigest()
    if len(set(observations.values())) != 1:
        raise ValueError(observations)
    if pilot:
        binary = work / "sed"
        subprocess.run(["clang-18", "-O2", "-Wl,--gc-sections", ROOT / "bridges/sed_main.c", ROOT / "bridges/sed_abi.c",
                        archives["candidate"], *flags, "-o", binary], check=True)
        command = {}
        for cc, ref in cli.items():
            report = work / (cc + ".json")
            subprocess.run(["python3", ROOT / "tests/sed-oracle-differential.py", "--gcc", ref, "--clang", binary,
                            "--output", report], check=True, stdout=subprocess.DEVNULL)
            r = json.loads(report.read_bytes())
            if not r["gcc_clang_exact"] or not r["comparisons"]:
                raise ValueError("incomplete sed command suite")
            command[cc] = r["comparisons"]
    return dict(archive_sha256={n:digest(p) for n,p in archives.items()}, api_outputs=observations,
                quote_calls_per_run=75, allocation_errors_per_run=5, driver_sha256=digest(driver),
                **({"public_commands": command} if pilot else {}))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("link", type=Path)
    p.add_argument("pilot", type=Path, nargs="?")
    a = p.parse_args()
    with TemporaryDirectory() as tmp:
        print(json.dumps(run(a.link, a.pilot, Path(tmp)), sort_keys=True, indent=2))
