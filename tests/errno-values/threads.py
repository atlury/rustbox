#!/usr/bin/env python3
"""Compare the Rust errno accessor with glibc in concurrent threads and signal handlers."""
# SPDX-License-Identifier: 0BSD
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
helper = ROOT / "compat/linux/errno.rs"
driver = Path(__file__).with_name("threads.c")
with TemporaryDirectory() as tmp:
    work = Path(tmp)
    glue = work / "errno.rs"
    glue.write_bytes(helper.read_bytes() + b"""
#[no_mangle]
extern "C" fn read_errno() -> i32 { rustbox_errno::get() }
#[no_mangle]
extern "C" fn write_errno(value: i32) { rustbox_errno::set(value) }
""")
    subprocess.run(["rustc", "--crate-type=staticlib", "--edition=2021", "-O", glue, "-o", work / "errno.a"], check=True)
    passed = []
    for cc in ("gcc", "clang-18"):
        for target in ("canonical", "rust"):
            exe = work / (cc + "-" + target)
            flags = ["-DCANONICAL"] if target == "canonical" else [work / "errno.a"]
            subprocess.run([cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", driver, *flags, "-pthread", "-o", exe],
                           check=True)
            for checked in (False, True):
                log = work / "memcheck"
                prefix = ["valgrind", "--error-exitcode=99", "--leak-check=full", "--log-file=" + str(log)] if checked else []
                run = subprocess.run([*prefix, exe], capture_output=True, check=True, timeout=180)
                if run.stdout != b"4 threads, 64 errno and signal rounds\n" or run.stderr:
                    raise ValueError((cc, target, run.stdout, run.stderr))
                if checked and "ERROR SUMMARY: 0 errors" not in log.read_text():
                    raise ValueError("errno comparison failed Memcheck")
                passed.append(dict(compiler=cc, target=target, memcheck=checked))
    print(json.dumps(dict(runs=passed, rounds_per_run=64, threads_per_run=4,
                          helper_sha256=sha256(helper.read_bytes()).hexdigest(),
                          driver_sha256=sha256(driver.read_bytes()).hexdigest()), indent=2, sort_keys=True))
