#!/usr/bin/env python3
"""Compare five GNU tar option tables, diagnostics, archive bytes and backup file contents."""
# SPDX-License-Identifier: GPL-3.0-or-later
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import tarfile
from tempfile import TemporaryDirectory

from build_tar_argmatch_tables import CANONICAL, TABLES, options, substitute
from test_tar_exclusion_tables import ENV, main

FLAGS = {
    "warning_args": "--warning", "backup_args": "--backup", "sort_mode_arg": "--sort",
    "hole_detection_args": "--hole-detection", "atime_preserve_args": "--atime-preserve",
}


def exercise(programs, directory, memcheck=False):
    # A single regular file with exactly two 512-byte blocks before the end marker.
    stream = BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        item = tarfile.TarInfo("member")
        item.size = 3
        tar.addfile(item, BytesIO(b"new"))
    archive = stream.getvalue()
    cases = []
    def check(flags, args, data=b"", *, succeeds=None, members=None, warning=None, backups=None, valgrind=False):
        baseline = None
        for label, exe in programs.items():
            with TemporaryDirectory(dir=directory) as temp:
                dest = Path(temp)
                if backups is not None:
                    (dest/"member").write_bytes(b"old")
                executable = exe[0]
                command = ["tar" if len(exe) == 1 else "rustbox", *exe[1:], *flags, *args]
                if valgrind and label == "candidate":
                    log = directory / "tar-options.memcheck.log"
                    command = ["valgrind", "--error-exitcode=99", "--leak-check=full",
                               "--errors-for-leak-kinds=definite,indirect", "--log-file="+str(log), *exe, *flags, *args]
                    executable = "valgrind"
                run = subprocess.run(command, executable=executable, input=data, capture_output=True, cwd=dest, env=ENV, timeout=180)
                files = {p.name: p.read_bytes() for p in sorted(dest.iterdir())}
                result = (run.returncode, run.stdout, run.stderr, files)
                if baseline is None:
                    baseline = result
                if (result != baseline or succeeds is not None and (run.returncode == 0) != succeeds
                        or members is not None and run.stdout != members
                        or warning is not None and (b"Terminating zero blocks missing" in run.stderr) != warning
                        or backups is not None and files != backups):
                    raise ValueError((label, flags, run.returncode, run.stderr[:180], list(files)))
                if valgrind and label == "candidate" and "ERROR SUMMARY: 0 errors" not in log.read_text():
                    raise ValueError("GNU tar option parsing failed Memcheck")
        status, out, err, files = baseline
        cases.append([flags, status, sha256(out).hexdigest(), sha256(err).hexdigest(),
                      {k:sha256(v).hexdigest() for k,v in files.items()}])
    create = ["-cf", "-", "--blocking-factor=1", "--files-from=/dev/null"]
    for canonical, tables in TABLES.values():
        for table in tables:
            names = options((CANONICAL / canonical).read_bytes(), table)
            flag = FLAGS[table].encode() + b"="
            values = sorted({v for name in names for v in (name, name[:1], name[:-1])} | {b"", b"bogus", b"raw-\xff"})
            for value in values:
                # An empty backup policy is defined by gnulib. Prefix acceptance is decided by the oracle.
                succeeds = True if value in names else False if value in (b"bogus", b"raw-\xff") else None
                check([os.fsdecode(flag+value)], create, succeeds=succeeds)
    for flags, wanted in [
        (["--warning=none"],False), (["--warning=missing-zero-blocks"],True),
        (["--warning=missing-z","--warning=no-missing-zero-blocks"],False),
        (["--warning=none","--warning=missing-z"],True),
    ]:
        check(flags, ["-tf","-"], archive[:1024], succeeds=True, members=b"member\n", warning=wanted)
    for mode, backup in [("off",None),("simple","member~"),("existing","member~"),("numbered","member.~1~")]:
        wanted={"member":b"new"}
        if backup:
            wanted[backup]=b"old"
        check(["--backup="+mode], ["-xf","-"], archive, succeeds=True, backups=wanted)
    flags=["--sort=nam","--atime-preserve=rep","--hole-detection=ra","--warning=alone-z","--backup=simp"]
    check(flags, create, succeeds=True, valgrind=memcheck)
    return dict(tables=len(FLAGS), cases=len(cases), failed_options=sum(row[1]!=0 for row in cases),
                observations_sha256=sha256(json.dumps(cases,sort_keys=True).encode()).hexdigest(),
                memcheck_runs=int(memcheck))


if __name__ == "__main__":
    main(Path(__file__).name, substitute, exercise)
