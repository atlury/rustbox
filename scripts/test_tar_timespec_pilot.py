#!/usr/bin/env python3
"""Compare tar's timestamp APIs, filesystem effects, tar and rmt with canonical GNU builds."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from build_tar_timespec_pilot import ARCHIVE
from check_cargo_private_inlines import ROOT, digest


def compare(pilot, link):
    row = json.loads((pilot / "pilot.json").read_bytes())
    archive = Path(ARCHIVE)
    release = json.loads(link.read_bytes())
    if (row["archive"] != ARCHIVE or row["control_binary_sha256"] != release["binary"]["sha256"]
            or row["control_sha256"] != release["source_library_sha256"][ARCHIVE]
            or digest(ROOT / archive) != row["control_sha256"] or digest(pilot / archive.name) != row["candidate_sha256"]):
        raise ValueError("timestamp candidate or control differs from compiler receipt")
    pkg = ROOT / "work/analysis/tar-1.35"
    oracle = pkg / "oracle"
    residue = sorted((pkg / "hybrid-artifacts/c-residue").glob("*.o"))
    driver = ROOT / "tests/tar-timestamps/callers.c"
    with TemporaryDirectory() as temp:
        tmp = Path(temp)
        expected = None
        results = {}
        for kind, lib in (("gcc", Path("/rustbox-tar/source-gcc/gnu/libgnu.a")),
                          ("clang", Path("/rustbox-tar/source-clang/gnu/libgnu.a")),
                          ("parent", ROOT / archive), ("candidate", pilot / archive.name)):
            tested = tmp / kind
            tested.mkdir()
            objects = [*residue, lib] if kind in ("parent", "candidate") else [lib]
            subprocess.run(["cc", "-O2", "-Wl,--gc-sections", driver, *objects, "-lacl", "-ldl", "-lpthread", "-lm",
                            "-o", tested / "probe"], check=True)
            output = subprocess.check_output([tested / "probe"], cwd=tested)
            if len(output.splitlines()) != 732 or (expected is not None and expected != output):
                raise ValueError(f"tar timestamp status, errno or filesystem timestamps differ for {kind}")
            expected = output
            results[kind] = digest(lib)
        mem = tmp / "memcheck"
        mem.mkdir()
        output = subprocess.check_output(["valgrind", "--leak-check=full", "--error-exitcode=99",
            "--log-file=valgrind.log", tmp / "candidate/probe"], cwd=mem)
        if output != expected or "ERROR SUMMARY: 0 errors" not in (mem / "valgrind.log").read_text():
            raise ValueError("Memcheck or filesystem timestamps differ")
        binary_hashes = {}
        for utility, scope in (("tar", "bin"), ("rmt", "libexec")):
            exe = tmp / "usr" / scope / utility
            exe.parent.mkdir(parents=True)
            subprocess.run(["clang-18", "-O2", "-g", "-fno-omit-frame-pointer", "-ffunction-sections", "-fdata-sections",
                f"-DRUSTBOX_ENTRY=rustbox_{utility}_main", "-Wl,--gc-sections", "-o", exe, ROOT / "bridges/tar_main.c",
                *residue, pilot / archive.name, "-lacl", "-ldl", "-lpthread", "-lm", "-lrt", "-lutil"], check=True)
            binary_hashes[utility] = digest(exe)
        public = {}
        driver_cli = ROOT / "tests/tar-oracle-differential.py"
        for compiler in ("gcc", "clang"):
            out = tmp / (compiler + ".json")
            subprocess.run(["python3", driver_cli, "--gcc-root", oracle / (compiler + "-root"), "--clang-root", tmp,
                            "--output", out], check=True, stdout=subprocess.DEVNULL)
            checks = json.loads(out.read_bytes())
            if checks["cases"] <= 0 or checks["cases"] != checks["passed"]:
                raise ValueError(f"tar/rmt public command results differ from canonical {compiler}")
            public[compiler] = checks["passed"]
        return dict(row, timestamp_cases_per_build=732, timestamp_probe_sha256=digest(driver),
                    timestamp_output_sha256=hashlib.sha256(expected).hexdigest(), tested_archives=results,
                    memcheck_cases=732, canonical_cli_cases=public, cli_driver_sha256=digest(driver_cli),
                    candidate_executables=binary_hashes)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pilot", type=Path)
    parser.add_argument("link", type=Path)
    parser.add_argument("--mounted", action="store_true")
    args = parser.parse_args()
    if args.mounted:
        print(json.dumps(compare(args.pilot, args.link), indent=2, sort_keys=True))
    else:
        subprocess.run(["docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64",
            "-v", f"{ROOT}:/work:ro", "-v", "rustbox-tar-1.35:/rustbox-tar:ro",
            "rustbox-e2fsprogs:2026-11-24", "python3", "-B", "/work/scripts/test_tar_timespec_pilot.py",
            Path("/work") / args.pilot.resolve().relative_to(ROOT), Path("/work") / args.link.resolve().relative_to(ROOT),
            "--mounted"], check=True)
