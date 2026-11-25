#!/usr/bin/env python3
"""Switch between four thread-local locales while comparing all GNU classification masks."""
# SPDX-License-Identifier: 0BSD
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
base = json.loads((ROOT / "evidence/glibc-ctype-values.json").read_bytes())
if sha256((ROOT / "compat/linux/ctype.rs").read_bytes()).hexdigest() != base["helper_sha256"]:
    raise ValueError("locale helper differs")
with TemporaryDirectory() as tmp:
    d = Path(tmp)
    rust = d / "libctype.a"
    subprocess.run(["rustc", "--edition=2021", "--crate-type=staticlib", "-Copt-level=2", HERE / "probe.rs", "-o", rust], check=True)
    checks = {}
    for cc in ("gcc", "clang-18"):
        exe = d / cc
        subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", "-pthread",
                        HERE / "thread_local.c", rust, "-ldl", "-lm", "-o", exe], check=True)
        for mode in ("native", "memcheck"):
            log = d / "log"
            prefix = ["valgrind", "--error-exitcode=99", "--leak-check=full", "--errors-for-leak-kinds=definite,indirect",
                      "--log-file=" + str(log)] if mode == "memcheck" else []
            data = subprocess.check_output([*prefix, exe], timeout=180)
            rows = [list(map(int, line.split())) for line in data.splitlines()]
            if (len(rows) != 4 or [r[0] for r in rows] != list(range(4)) or any(r[1] != 32*256*12 or not r[2] for r in rows)
                    or mode == "memcheck" and "ERROR SUMMARY: 0 errors" not in log.read_text()):
                raise ValueError("incorrect classification or memory error")
            checks[cc + "/" + mode] = rows
    if any(r != checks["gcc/native"] for r in checks.values()):
        raise ValueError("threaded classification totals differ")
    print(json.dumps(dict(helper_sha256=base["helper_sha256"], locales=["C","fr_FR.iso88591","C.utf8","sv_SE.iso88591"],
                          rounds_per_thread=32, threads=4, comparisons_per_run=4*32*256*12,
                          results=checks), sort_keys=True, indent=2))
