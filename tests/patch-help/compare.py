#!/usr/bin/env python3
"""Compare the GNU patch help catalog, its stream behavior and patch file operation results."""
# SPDX-License-Identifier: GPL-3.0-or-later
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


def compare(programs, work, row, *, memcheck_command=None):
    public = {}
    for cc in ("gcc", "clang"):
        report = work / (cc + ".json")
        subprocess.run([sys.executable, ROOT / "tests/patch-oracle-differential.py", "--gcc", programs[cc],
                        "--clang", programs["candidate"], "--output", report], check=True, stdout=subprocess.DEVNULL)
        data = json.loads(report.read_bytes())
        if not data["gcc_clang_exact"] or not data["records"] or not all(r["exact"] for r in data["records"]):
            raise ValueError("patch file application differs")
        public[cc] = len(data["records"])
    expected = {}
    memchecks = 0
    locales = subprocess.check_output(["locale", "-a"], text=True).splitlines()
    for target, binary in programs.items():
        for loc in locales:
            env = dict(os.environ, LC_ALL=loc, TZ="UTC")
            for case, argv, full in (("help", ["--help"], False), ("bad-option", ["--rustbox-unknown"], False),
                                     ("full-output", ["--help"], True)):
                with open(os.devnull if not full else "/dev/full", "wb") as sink:
                    result = subprocess.run(["patch", *argv], executable=binary, stdin=subprocess.DEVNULL, env=env,
                                            stdout=sink if full else subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
                values = [result.returncode, sha256(result.stdout or b"").hexdigest(), sha256(result.stderr).hexdigest()]
                key = loc + "/" + case
                if expected.setdefault(key, values) != values:
                    raise ValueError((target, key, "exit or output differs"))
                if loc == "C" and case == "help":
                    header, text = result.stdout.split(b"\n\n", 1)
                    packed = text.replace(b"\n", b"\0")
                    if (result.returncode or result.stderr or not header.startswith(b"Usage: patch ")
                            or packed.count(b"\0") != row["lines"] or len(packed) != row["catalog_bytes"]
                            or sha256(packed).hexdigest() != row["catalog_sha256"]):
                        raise ValueError("catalog differs from canonical GNU patch standard output")
        log = work / (target + "-memcheck.log")
        checked = subprocess.run(["valgrind", "--error-exitcode=99", "--leak-check=full",
                                  "--errors-for-leak-kinds=definite,indirect,possible", "--log-file=" + str(log),
                                  *(memcheck_command if target == "candidate" and memcheck_command else [binary]),
                                  "--help"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.PIPE, timeout=120)
        if checked.returncode or checked.stderr or "ERROR SUMMARY: 0 errors" not in log.read_text():
            raise ValueError((target, "Memcheck failed"))
        memchecks += 1
    return dict(file_cases=public, locales=sorted(locales), help_or_error_cases=len(expected),
                outputs_sha256=sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest(), memcheck_runs=memchecks)


def canonical_programs():
    oracle = ROOT / "work/analysis/patch-2.8/oracle"
    pins = json.loads((ROOT / "evidence/patch-2.8-oracle.json").read_bytes())["binaries"]
    programs = {cc: oracle / ("patch-" + cc) for cc in ("gcc", "clang")}
    if any(digest(binary) != pins[cc]["sha256"] for cc, binary in programs.items()):
        raise ValueError("canonical GNU patch differs")
    return programs


def run(link, pilot, work):
    row = json.loads((pilot / "pilot.json").read_bytes())
    parent = json.loads(link.read_bytes())
    original = ROOT / row["archive"]
    candidate = pilot / original.name
    if (digest(original) != row["control_sha256"] or digest(candidate) != row["candidate_sha256"]
            or parent["source_library_sha256"].get(row["archive"]) != row["control_sha256"]
            or parent["binary"]["sha256"] != row["control_binary_sha256"]):
        raise ValueError("GNU patch archive differs from the verified inputs")
    programs = canonical_programs()
    for target, archive in (("parent", original), ("candidate", candidate)):
        binary = work / target
        subprocess.run(["clang-18", "-O2", "-Wl,--gc-sections", "-o", binary, ROOT / "bridges/patch_main.c",
                        archive, "-lattr", "-ldl", "-lpthread", "-lm"], check=True)
        programs[target] = binary
    return compare(programs, work, row)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("link", type=Path)
    p.add_argument("pilot", type=Path)
    args = p.parse_args()
    with TemporaryDirectory() as temp:
        print(json.dumps(run(args.link, args.pilot, Path(temp)), indent=2, sort_keys=True))
