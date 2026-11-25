#!/usr/bin/env python3
"""Compare full glibc classification masks and errno in every installed Linux locale."""
# SPDX-License-Identifier: 0BSD
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent.resolve()
locales = sorted(set(subprocess.check_output(["locale", "-a"], text=True).splitlines()))
block = 256 * 12 * 4
if not {"C", "C.utf8", "fr_FR.iso88591", "sv_SE.iso88591"} <= set(locales):
    raise ValueError("expected the project Linux locale set")
with TemporaryDirectory() as tmp:
    folder = Path(tmp)
    archive = folder / "libctype.a"
    subprocess.run(["rustc", "--edition=2021", "--crate-type=staticlib", "-Copt-level=2", HERE / "probe.rs",
                    "-o", archive], check=True)
    observed = {}
    memchecks = 0
    for cc in ("gcc", "clang-18"):
        binary = folder / cc
        subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", HERE / "probe.c", archive,
                        "-lpthread", "-ldl", "-lm", "-o", binary], check=True)
        for checker in ([], ["valgrind", "--leak-check=no", "--error-exitcode=99", "--log-file=" + str(folder / "log")]):
            data = subprocess.check_output([*checker, binary, *locales])
            if len(data) != len(locales) * block:
                raise ValueError("incomplete classification corpus")
            rows = {n: sha256(data[i*block:(i+1)*block]).hexdigest() for i, n in enumerate(locales)}
            if observed and observed != rows or rows["C"] == rows["fr_FR.iso88591"]:
                raise ValueError("locale dependent classification masks differ across builds or did not change")
            if checker:
                if "ERROR SUMMARY: 0 errors" not in (folder / "log").read_text():
                    raise ValueError("Memcheck failure")
                memchecks += 1
            observed = rows
    print(json.dumps(dict(locales=observed, byte_values=256, masks=12, comparisons_per_run=len(locales)*256*12,
                          compilers=["gcc", "clang-18"], memcheck_runs=memchecks,
                          helper_sha256=sha256((ROOT / "compat/linux/ctype.rs").read_bytes()).hexdigest()), sort_keys=True, indent=2))
