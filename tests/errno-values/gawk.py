#!/usr/bin/env python3
"""Exercise GNU awk's strtoul and MPFR errno checks in the complete engine archive."""
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


def profiles():
    for width in ("1 2", "1:2 2", "0", "0:1", "1:0", "*", "1 *", "x", "1:", "-1",
                  "18446744073709551615", "18446744073709551616", "18446744073709551616:1"):
        yield "width-" + width, ["-v", "FIELDWIDTHS=" + width, "{print NF, $1, $2}"], b"abcdef\n"
    for name, mode in (("decimal", []), ("non-decimal", ["--non-decimal-data"])):
        yield name, ["-M", *mode, "-v", "PREC=160", '{print typeof($1), ($1+0), strtonum($1)}'], (
            b"0\n-0\n+1\n0123\n0xFE\n0x1.fp2\n9007199254740993\n-18446744073709551616\n"
            b"1.0000000000000000000003\n1e100\n1e-100\n1e+\n1.2bad\nNaN\n+inf\n")
    yield "source-error", ["-f", os.fsdecode(b"missing-\xff.awk")], b""
    yield "errno-io", ['BEGIN { n = getline s < "missing"; print n, ERRNO; print close("missing"), ERRNO }'], b""


def compare(link, pilot, work, *, byte_keys=False):
    selected = json.loads(link.read_bytes())
    key, = [k for k in selected["source_library_sha256"] if Path(k).name.startswith("libgawk_") and k.endswith(".a")]
    pma = "build/gawk-5.4.0-hybrid/c-residue/pma.o"
    archives = {"parent": ROOT / key}
    if any(digest(ROOT / k) != selected["source_library_sha256"][k] for k in (pma, key)):
        raise ValueError("GNU awk archive or PMA input differs")
    if pilot:
        row = json.loads((pilot / "pilot.json").read_bytes())
        archives["candidate"] = pilot / Path(key).name
        if (row["archive"] != key or row["control_sha256"] != digest(archives["parent"])
                or row["control_binary_sha256"] != selected["binary"]["sha256"]
                or digest(archives["candidate"]) != row["candidate_sha256"]):
            raise ValueError("wrong GNU awk candidate")
    programs = {}
    for cc in ("gcc", "clang"):
        directory = Path("/rustbox-gawk/oracle-" + cc)
        installed = ROOT / "work/analysis/gawk-5.4.0/oracle" / (cc + "-root/usr/bin/gawk")
        if digest(directory / "gawk") != digest(installed):
            raise ValueError("canonical GNU awk differs")
        programs[cc] = directory / "gawk"
    for name, archive in archives.items():
        folder = work / name
        folder.mkdir()
        exe = folder / "gawk"
        subprocess.run(["clang-18", "-O2", "-Wl,--gc-sections", "-o", exe, ROOT / "bridges/gawk_main.c",
                        ROOT / "bridges/grep_abi.c", ROOT / pma, archive, "-lreadline", "-lmpfr", "-lgmp",
                        "-ldl", "-lpthread", "-lm"], check=True)
        programs[name] = exe
        (folder / "extension").symlink_to(ROOT / "build/gawk-5.4.0-hybrid/extension")
    if byte_keys:
        sys.path.insert(0, str(ROOT / "tests/ctype-values"))
        import gawk_keys
        return dict(archives={name: digest(path) for name, path in archives.items()},
                    canonical={cc: digest(programs[cc]) for cc in ("gcc", "clang")}, **gawk_keys.run(programs, work))
    target = "candidate" if pilot else "parent"
    public = {}
    for cc in ("gcc", "clang"):
        report = work / (cc + ".json")
        subprocess.run([sys.executable, ROOT / "tests/gawk-oracle-differential.py", "--gcc-build", programs[cc].parent,
                        "--clang-build", programs[target].parent, "--output", report], check=True, stdout=subprocess.DEVNULL)
        counts = json.loads(report.read_bytes())
        if not counts["cases"] or counts["cases"] != counts["passed"]:
            raise ValueError("incomplete GNU awk command suite")
        public[cc] = counts["passed"]
    results = {}
    memory = 0
    for label, args, stdin in profiles():
        baseline = None
        for name, binary in programs.items():
            for checked in ([False, True] if label in ("width-18446744073709551616:1", "non-decimal", "errno-io") else [False]):
                log = work / "memcheck"
                # The same argv[0] reaches all engines, including under Valgrind.
                entry = work / "gawk"
                entry.symlink_to(binary)
                cmd = ["./gawk", *args]
                if checked:
                    cmd = ["valgrind", "--leak-check=no", "--error-exitcode=99", "--log-file=" + str(log), *cmd]
                run = subprocess.run(cmd, cwd=work, env=dict(os.environ, LC_ALL="C", TZ="UTC0"),
                                     input=stdin, capture_output=True, timeout=90)
                entry.unlink()
                value = (run.returncode, run.stdout, run.stderr)
                if (run.returncode < 0 or run.returncode == 99 or baseline is not None and value != baseline
                        or checked and "ERROR SUMMARY: 0 errors" not in log.read_text()):
                    raise ValueError((label, name, checked, value, baseline))
                baseline = value
                memory += int(checked)
        results[label] = dict(status=baseline[0], stdout_sha256=sha256(baseline[1]).hexdigest(),
                              stderr_sha256=sha256(baseline[2]).hexdigest())
    if (results["width-1:2 2"]["status"] or results["non-decimal"]["status"] or results["errno-io"]["status"]
            or not results["width-18446744073709551616:1"]["status"] or not results["source-error"]["status"]):
        raise ValueError("canonical GNU awk success or error cases changed")
    return dict(archives={name: digest(path) for name, path in archives.items()},
                canonical={cc: digest(programs[cc]) for cc in ("gcc", "clang")}, public=public,
                profiles=results, memcheck_runs=memory)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("link", type=Path)
    p.add_argument("pilot", type=Path, nargs="?")
    p.add_argument("--byte-keys", action="store_true", help="compare numeric and byte-string array indices across locales")
    a = p.parse_args()
    with TemporaryDirectory() as tmp:
        print(json.dumps(compare(a.link, a.pilot, Path(tmp), byte_keys=a.byte_keys), indent=2, sort_keys=True))
