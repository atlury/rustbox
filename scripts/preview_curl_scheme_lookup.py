#!/usr/bin/env python3
"""Relink the real multicall curl and compare scheme handling with pinned GCC and Clang builds."""
# SPDX-License-Identifier: curl
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
from tempfile import TemporaryDirectory
import subprocess

from build_curl_scheme_lookup import HELPER, canonical_lookup
from check_cargo_private_inlines import ROOT, digest
from check_unused_type_commands import run_suite
from preview_cargo_multicall import preview
from preview_curl_month_array import namespace


def exercise(elf, stage):
    with TemporaryDirectory() as tmp:
        return public_commands(elf, Path(tmp))


def public_commands(elf, stage):
    package = "curl-8.23.0"
    oracle = ROOT / "work/analysis" / package / "oracle"
    pins = json.loads((ROOT / "evidence" / (package + "-oracle.json")).read_bytes())["binaries"]
    local = stage / "rustbox"
    shutil.copy2(elf, local)
    if digest(local) != digest(elf):
        raise ValueError("local multicall copy differs")
    elf = local
    public = stage / "as-curl" / "curl"
    public.parent.mkdir()
    public.symlink_to(elf)
    engines = [[oracle / f"curl-{cc}"] for cc in ("gcc", "clang")]
    if any(digest(cmd[0]) != pins[cc]["sha256"] for cmd, cc in zip(engines, ("gcc", "clang"))):
        raise ValueError("unexpected upstream curl executable")
    for cc, cmd in zip(("gcc", "clang"), engines):
        dest = stage / cc / "curl"
        dest.parent.mkdir()
        shutil.copy2(cmd[0], dest)
        if digest(dest) != pins[cc]["sha256"]:
            raise ValueError("local canonical curl copy differs")
        cmd[0] = dest
    engines.extend([[public], [elf, "curl"]])
    fixture = stage / "scheme-input"
    fixture.write_bytes(b"scheme comparison\x00\xff\n")
    url = fixture.as_uri()
    names = re.findall(rb"return &Curl_scheme_([a-z0-9]+);", canonical_lookup())
    cases = []
    for token in [*names, b"x", b"unknown", b"filex", b"fi\xffle"]:
        cases.extend([["--proto", b"=" + token, url],
                      ["--proto", b"=" + token.upper(), url],
                      ["--proto", "=file", "--proto-redir", b"=" + token, url]])
    cases += [[s + url[4:]] for s in ["FILE", "fILe"]]
    env = dict(LC_ALL="C", PATH="/usr/bin:/bin", HOME=str(stage))
    outcomes = []
    for args in cases:
        runs = []
        for cmd in engines:
            proc = subprocess.run([*cmd, "--disable", "--silent", "--show-error", *args],
                                  env=env, capture_output=True, timeout=90)
            runs.append((proc.returncode, proc.stdout, proc.stderr))
        if len(set(runs)) != 1:
            raise ValueError(f"scheme behavior differs for {args!r}: {runs!r}")
        code, out, err = runs[0]
        outcomes.append([code, out.hex(), err.hex()])
    suites = dict(run_suite(package, cc, elf, stage / ("oracle-" + cc)) for cc in ("gcc", "clang"))
    return dict(public_cases=len(cases), commands_per_case=len(engines), canonical_suites=suites,
                observed_sha256=sha256(json.dumps(outcomes).encode()).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("control", "log", "pilot", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    row = json.loads((args.pilot / "pilot.json").read_bytes())
    if row.get("helper_sha256") != digest(HELPER) or row.get("raw_pointer_types_removed", 0) <= 0:
        raise ValueError("expected a verified archive containing the checked scheme lookup")
    preview(args.control, args.log, args.pilot, args.output, row, namespace, exercise)
