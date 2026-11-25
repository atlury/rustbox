#!/usr/bin/env python3
"""Verify every offered output byte, command frontend and boundary length against upstream LZ4."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from build_lz4_dictionary_pilot import CANONICAL, C_SHA
from check_cargo_private_inlines import ROOT, digest


def check(link, pilot):
    release = json.loads(link.read_bytes())
    row = json.loads((pilot / "pilot.json").read_bytes())
    key = row["archive"]
    parent, candidate = ROOT / key, pilot / Path(key).name
    if (digest(CANONICAL) != C_SHA or row["canonical_sha256"] != C_SHA
            or release["binary"]["sha256"] != row["control_binary_sha256"]
            or release["source_library_sha256"].get(key) != row["control_sha256"]
            or digest(parent) != row["control_sha256"] or digest(candidate) != row["candidate_sha256"]):
        raise ValueError("LZ4 source, archives or selected release changed")
    driver = ROOT / "tests/lz4-dictionary/blocks.c"
    with TemporaryDirectory() as tmp:
        work = Path(tmp)
        def compile_program(cc, dest, *inputs):
            subprocess.run([cc, "-O2", "-Wl,--gc-sections", "-I" + str(CANONICAL.parent), *inputs,
                            "-ldl", "-lpthread", "-lm", "-o", dest], check=True)
        expected = None
        for name, cc, library in (("gcc", "gcc", CANONICAL), ("clang", "clang-18", CANONICAL),
                                   ("parent", "clang-18", parent), ("candidate", "clang-18", candidate)):
            binary = work / name
            compile_program(cc, binary, driver, library)
            result = subprocess.run([binary], capture_output=True, check=True)
            if result.stderr != b"2625\n" or (expected is not None and expected != result.stdout):
                raise ValueError(f"generator output or coverage differs for {name}")
            expected = result.stdout
        log = work / "memcheck.log"
        checked = subprocess.run(["valgrind", "--leak-check=full", "--error-exitcode=99", "--log-file=" + str(log),
                                  work / "candidate"], capture_output=True, check=True)
        if checked.stdout != expected or checked.stderr != b"2625\n" or "ERROR SUMMARY: 0 errors" not in log.read_text():
            raise ValueError("LZ4 dictionary differs under Memcheck")
        frontends = work / "commands"
        frontends.mkdir()
        compile_program("clang-18", frontends / "lz4", ROOT / "bridges/lz4_main.c", candidate)
        for alias in ("unlz4", "lz4c", "lz4cat"):
            (frontends / alias).symlink_to("lz4")
        public = {}
        for compiler in ("gcc", "clang"):
            output = work / (compiler + ".json")
            subprocess.run(["python3", ROOT / "tests/lz4-oracle-differential.py",
                            "--gcc-directory", ROOT / "work/analysis/lz4-1.11.1/oracle" / compiler,
                            "--clang-directory", frontends, "--output", output], check=True, stdout=subprocess.DEVNULL)
            data = json.loads(output.read_bytes())
            if not data["cases"] or data["cases"] != data["passed"]:
                raise ValueError("LZ4 command comparison failed")
            public[compiler] = data["cases"]
        return dict(row, generator_cases=2625, memcheck_cases=2625, command_cases=public, result_bytes=len(expected),
                    result_sha256=sha256(expected).hexdigest(), driver_sha256=digest(driver))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("link", type=Path)
    p.add_argument("pilot", type=Path)
    a = p.parse_args()
    print(json.dumps(check(a.link, a.pilot), indent=2, sort_keys=True))
