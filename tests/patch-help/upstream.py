#!/usr/bin/env python3
"""Replay GNU patch's shipped Automake fixtures in private, unprivileged directories."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]


def run(elf, work):
    if os.getuid() == 0:
        raise ValueError("the read-only file fixtures require an unprivileged test user")
    release = json.loads((ROOT / "evidence/patch-2.8-oracle.json").read_bytes())
    source = ROOT / "work/upstream/patch-2.8"
    expectations = {}
    for cc in ("gcc", "clang"):
        log = (ROOT / f"work/analysis/patch-2.8/oracle/{cc}-check.log").read_bytes()
        if sha256(log).hexdigest() != release["tests"][cc]["log_sha256"]:
            raise ValueError("canonical patch test log differs")
        rows = {name:status for status, name in re.findall(r"^(PASS|XFAIL): ([\w-]+)$", log.decode(), re.M)}
        if expectations and expectations != rows:
            raise ValueError("canonical test outcomes differ")
        expectations = rows
    if Counter(expectations.values()) != {"PASS":47, "XFAIL":2}:
        raise ValueError("incomplete canonical upstream suite")
    snapshot = work / "rustbox"
    shutil.copyfile(elf, snapshot)
    snapshot.chmod(0o755)
    for mode in ("applet", "subcommand"):
        base = work / mode
        base.mkdir()
        directory = base / "tests"
        directory.mkdir()
        entry = base / "patch"
        if mode == "applet":
            entry.symlink_to(snapshot)
        else:
            # The upstream fixtures use the path in PATCH verbatim in diagnostics.
            # Rustbox resolves the applet basename and passes the original argument to GNU patch.
            entry.write_text("#!/bin/sh\nexec " + shlex.quote(str(snapshot)) + " " + shlex.quote(str(entry)) + ' "$@"\n')
            entry.chmod(0o755)
        env = dict(os.environ, abs_top_builddir=str(base), srcdir=str(source / "tests"),
                   PATCH=str(entry), LC_ALL="C", TZ="UTC")
        for name, status in sorted(expectations.items()):
            log = directory / (name + ".log")
            trs = directory / (name + ".trs")
            result = subprocess.run(["/bin/sh", source / "build-aux/test-driver", "--test-name", name,
                                     "--log-file", log, "--trs-file", trs, "--expect-failure",
                                     "yes" if status == "XFAIL" else "no", "--color-tests", "no", "--",
                                     "/bin/sh", source / "tests" / name], env=env, cwd=directory,
                                    capture_output=True, timeout=180)
            if result.returncode or (":test-result: " + status) not in trs.read_text().splitlines():
                raise ValueError((mode, name, result.stdout[-300:], result.stderr[-300:], log.read_bytes()[-1500:]))
    return dict(elf_sha256=sha256(snapshot.read_bytes()).hexdigest(), modes=["applet","subcommand"],
                cases_per_mode=len(expectations), passed_per_mode=47, expected_failures=sorted(n for n,s in expectations.items() if s=="XFAIL"))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("elf", type=Path)
    with TemporaryDirectory() as temp:
        print(json.dumps(run(p.parse_args().elf, Path(temp)), indent=2, sort_keys=True))
