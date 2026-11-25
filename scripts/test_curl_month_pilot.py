#!/usr/bin/env python3
"""Compare the selected curl archive at its public date API and command front end."""
# SPDX-License-Identifier: curl
import argparse
from datetime import datetime, timezone
from hashlib import sha256
from itertools import product
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from check_cargo_private_inlines import ROOT, digest


def cases():
    dates, required = [], []
    for i, month in enumerate(b"jan feb mar apr may jun jul aug sep oct nov dec".split(), 1):
        for letters in product(*[(c, c - 32) for c in month]):
            word = bytes(letters)
            required.append(int(datetime(2001, i, 5, 13, 14, 15, tzinfo=timezone.utc).timestamp()))
            dates.append(b"05 " + word + b" 2001 13:14:15 GMT")
    for word in [b"", b"j", b"ja", b"january", b"jann", b"xyz", b"\xffab", b"a\xffb", b"ab\xff", b"q" * 40]:
        dates.append(b"05 " + word + b" 2001 13:14:15 GMT")
    return b"\n".join(dates) + b"\n", required, len(dates)


def compare(pilot, link, case_set=cases):
    release = json.loads(link.read_bytes())
    row = json.loads((pilot / "pilot.json").read_bytes())
    parent = ROOT / row["archive"]
    changed = pilot / parent.name
    base = ROOT / "work/analysis/curl-8.23.0"
    oracle = base / "oracle"
    obj = base / "hybrid-artifacts/c-residue/mprintf.o"
    refs = json.loads((ROOT / "evidence/curl-8.23.0-oracle.json").read_bytes())["binaries"]
    if (release["binary"]["sha256"] != row["control_binary_sha256"] or digest(changed) != row["candidate_sha256"]
            or release["source_library_sha256"][row["archive"]] != digest(parent) or digest(parent) != row["control_sha256"]
            or release["source_library_sha256"][str(obj.relative_to(ROOT))] != digest(obj)):
        raise ValueError("curl candidate or retained object differs from selected release")
    inputs, required, count = case_set()
    driver = ROOT / "tests/curl-calendar/getdate.c"
    flags = ["-ldl", "-lpthread", "-lm", "-lrt"]
    with TemporaryDirectory() as temp:
        work = Path(temp)
        output = None
        public = {}
        for name, archive in (("gcc", oracle / "libcurl-gcc.a"), ("clang", oracle / "libcurl-clang.a"),
                              ("parent", parent), ("candidate", changed)):
            canonical = name in refs
            if canonical and (digest(archive) != refs[name]["static_libcurl_sha256"]
                              or digest(oracle / ("curl-" + name)) != refs[name]["sha256"]):
                raise ValueError("unexpected canonical curl inputs")
            exe = work / name
            subprocess.run(["clang-18", "-O2", "-Wl,--gc-sections", "-o", exe, driver,
                            *([] if canonical else [obj]), archive, *flags], check=True)
            data = subprocess.check_output([exe], input=inputs, env=dict(os.environ, TZ="UTC", LC_ALL="C"))
            values = list(map(int, data.splitlines()))
            if len(values) != count or values[:len(required)] != required or (output is not None and output != data):
                raise ValueError(f"curl_getdate disagrees on {name}")
            output = data
        log = work / "memcheck.log"
        data = subprocess.check_output(["valgrind", "--leak-check=full", "--error-exitcode=99", "--log-file=" + str(log),
                                        work / "candidate"], input=inputs, env=dict(os.environ, TZ="UTC", LC_ALL="C"))
        if data != output or "ERROR SUMMARY: 0 errors" not in log.read_text():
            raise ValueError("date results or Memcheck changed")
        cli = work / "curl"
        subprocess.run(["clang-18", "-O2", "-Wl,--gc-sections", "-o", cli, ROOT / "bridges/curl_main.c",
                        obj, changed, *flags], check=True)
        for compiler in ("gcc", "clang"):
            result = work / (compiler + ".json")
            subprocess.run(["python3", ROOT / "tests/curl-oracle-differential.py", "--gcc", oracle / ("curl-" + compiler),
                            "--clang", cli, "--output", result], check=True, stdout=subprocess.DEVNULL)
            checked = json.loads(result.read_bytes())
            if not checked["cases"] or checked["cases"] != checked["passed"]:
                raise ValueError("incomplete curl command comparison")
            public[compiler] = checked["cases"]
        return dict(row, public_date_cases_per_build=count, calendar_known_answers=len(required), memcheck_date_cases=count,
                    public_cli=public, date_inputs_sha256=sha256(inputs).hexdigest(), date_outputs_sha256=sha256(output).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pilot", type=Path)
    parser.add_argument("link", type=Path)
    args = parser.parse_args()
    print(json.dumps(compare(args.pilot, args.link), sort_keys=True, indent=2))
