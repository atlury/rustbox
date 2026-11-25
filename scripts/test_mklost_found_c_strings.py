#!/usr/bin/env python3
"""Check GNU/Linux E2fsprogs mklost+found with const-checked C strings on its original compiler."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
from tempfile import TemporaryDirectory

from check_cargo_private_inlines import ROOT, digest


def exercise(exe, parent, case, checker=()):
    with TemporaryDirectory(dir=parent) as folder:
        cwd = Path(folder)
        lost = cwd / "lost+found"
        if case == "directory":
            lost.mkdir()
            (lost / "keep").write_bytes(b"unchanged\xff")
        elif case == "file":
            lost.write_bytes(b"bytes\x00")
        elif case == "symlink":
            lost.symlink_to("absent")
        args = {"help": ["--help"], "args": ["bad", "argument"], "raw-arg": [b"\xff"]}.get(case, [])
        command = subprocess.run([*checker, exe, *args], cwd=cwd, capture_output=True, timeout=120,
                                 env=dict(os.environ, LC_ALL="C", TZ="UTC"))
        effect = []
        for path in sorted(cwd.rglob("*")):
            info = path.lstat()
            payload = str(path.readlink()) if path.is_symlink() else path.read_bytes() if path.is_file() else None
            effect.append((str(path.relative_to(cwd)), info.st_mode, payload))
        return command.returncode, command.stdout, command.stderr, effect


def compare(pilot, link):
    row = json.loads((pilot / "pilot.json").read_bytes())
    key = row["archive"]
    release = json.loads(link.read_bytes())
    archive = ROOT / key
    candidate = pilot / archive.name
    if (archive.name != "libmklost_found_audit.a" or row["control_binary_sha256"] != release["binary"]["sha256"]
            or row["control_sha256"] != release["source_library_sha256"][key] or digest(archive) != row["control_sha256"]
            or digest(candidate) != row["candidate_sha256"] or row["legacy_compiler"] != "nightly-2023-04-15"):
        raise ValueError("C-string archive or selected compiler differs")
    base = Path("/rustbox-e2fsprogs")
    canonical = [base / ("stage-" + c) / "usr/sbin/mklost+found" for c in ("gcc", "clang-18")]
    cases = ["create", "directory", "file", "symlink", "help", "args", "raw-arg"]
    with TemporaryDirectory() as folder:
        tmp = Path(folder)
        exes = []
        for name, lib in (("control", archive), ("candidate", candidate)):
            exe = tmp / name / "mklost+found"
            exe.parent.mkdir()
            subprocess.run(["clang-18", "-O2", "-g", "-fno-omit-frame-pointer", "-ffunction-sections", "-fdata-sections",
                "-Wl,--gc-sections", "-DRUSTBOX_E2FSPROGS_ENTRY=rustbox_e2fsprogs_mklost_found_main", "-o", exe,
                ROOT / "bridges/e2fsprogs_program_main.c", lib, "-lblkid", "-luuid", "-lfuse3", "-ldl", "-lpthread", "-lm"], check=True)
            exes.append(exe)
        for case in cases:
            expected = exercise(canonical[0], tmp, case)
            if expected[0] != int(case != "create") or (case == "create" and expected[3] != [("lost+found", stat.S_IFDIR | 0o700, None)]):
                raise ValueError(f"unexpected canonical behaviour for {case}")
            for exe in (canonical[1], *exes):
                if exercise(exe, tmp, case) != expected:
                    raise ValueError(f"{case} differs for {exe}")
            if case in ("create", "file"):
                report = tmp / (case + ".log")
                check = ["valgrind", "--leak-check=full", "--error-exitcode=99", "--log-file=" + str(report)]
                if exercise(exes[-1], tmp, case, check) != expected or "ERROR SUMMARY: 0 errors" not in report.read_text():
                    raise ValueError("Memcheck differs from canonical mklost+found")
        return dict(row, cases=cases, memcheck_runs=2, standalone_sha256={exe.parent.name: digest(exe) for exe in exes},
                    gcc_sha256=digest(canonical[0]), clang_sha256=digest(canonical[1]))


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
            "-v", f"{ROOT}:/work:ro", "-v", "rustbox-e2fsprogs-1.47.4:/rustbox-e2fsprogs:ro",
            "rustbox-e2fsprogs:2026-11-24", "python3", "-B", "/work/scripts/test_mklost_found_c_strings.py",
            Path("/work") / args.pilot.resolve().relative_to(ROOT), Path("/work") / args.link.resolve().relative_to(ROOT),
            "--mounted"], check=True)
