#!/usr/bin/env python3
"""Compare GNU hostname's public argp formatting on the original and checked archives."""
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


def compare(link, pilot, work):
    j = json.loads(link.read_bytes())
    key, = [n for n in j["source_library_sha256"] if n.endswith("/libhostname_audit.a")]
    archive = ROOT / key
    r = json.loads((pilot / "pilot.json").read_bytes())
    candidate = pilot / archive.name
    if (digest(archive) != j["source_library_sha256"][key] or r["archive"] != key or r["control_sha256"] != digest(archive)
            or r["candidate_sha256"] != digest(candidate) or r["control_binary_sha256"] != j["binary"]["sha256"]):
        raise ValueError("unexpected hostname input")
    programs = {cc: Path("/rustbox-inetutils") / ("oracle-" + cc) / "src/hostname" for cc in ("gcc", "clang")}
    for n, path in (("parent", archive), ("candidate", candidate)):
        directory = work / n
        directory.mkdir()
        exe = directory / "hostname"
        subprocess.run(["clang-18", "-O2", "-Wl,--gc-sections", "-DRUSTBOX_INETUTILS_ENTRY=rustbox_inetutils_hostname_main",
                        "-o", exe, ROOT / "bridges/inetutils_program_main.c", path, "-ldl", "-lpthread", "-lm", "-lrt", "-lutil"], check=True)
        programs[n] = exe
    hashes = {}
    memory = 0
    for loc in ("C", "C.utf8", "fr_FR.iso88591", "ja_JP.eucjp"):
        for fmt in ("", "rmargin=43", "rmargin=60,opt-doc-col=22", "rmargin=93,no-dup-args-note"):
            for option in ("--help", "--usage", "--version"):
                expected = None
                for n, exe in programs.items():
                    entry = work / "hostname"
                    entry.symlink_to(exe)
                    env = dict(os.environ, LC_ALL=loc, TZ="UTC0")
                    if fmt:
                        env["ARGP_HELP_FMT"] = fmt
                    for check in ([False, True] if loc == "C" and option == "--help" and fmt in ("", "rmargin=43") else [False]):
                        cmd = ["./hostname", option]
                        log = work / "memcheck"
                        if check:
                            cmd = ["valgrind", "--leak-check=no", "--error-exitcode=99", "--log-file="+str(log), *cmd]
                        proc = subprocess.run(cmd, cwd=work, env=env, capture_output=True, timeout=90, stdin=subprocess.DEVNULL)
                        result = proc.stdout, proc.stderr
                        if (proc.returncode or not proc.stdout or expected is not None and expected != result
                                or check and "ERROR SUMMARY: 0 errors" not in log.read_text()):
                            raise ValueError((loc, fmt, option, n, check, proc.returncode, proc.stderr[:200]))
                        expected = result
                        memory += int(check)
                    entry.unlink()
                hashes["/".join([loc, fmt, option])] = [sha256(v).hexdigest() for v in expected]
    if hashes["C//--help"] == hashes["C/rmargin=43/--help"]:
        raise ValueError("selected margins did not exercise word wrapping")
    return dict(profiles=hashes, memcheck_runs=memory, archives=dict(parent=digest(archive), candidate=digest(candidate)),
                canonical={cc: digest(programs[cc]) for cc in ("gcc", "clang")})


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("link", type=Path)
    p.add_argument("pilot", type=Path)
    a = p.parse_args()
    with TemporaryDirectory() as tmp:
        print(json.dumps(compare(a.link, a.pilot, Path(tmp)), indent=2, sort_keys=True))
