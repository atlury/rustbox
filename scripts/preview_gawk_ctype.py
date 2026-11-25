#!/usr/bin/env python3
"""Compare checked GNU awk array keys in the complete multicall and both public dispatch modes."""
# SPDX-License-Identifier: 0BSD
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys

from check_cargo_private_inlines import ROOT, digest
from link_rustbox_multicall import namespace_gawk_library
from preview_cargo_multicall import preview

sys.path.insert(0, str(ROOT / "tests/ctype-values"))
import gawk_keys


def namespace(archive, residues, release, stage):
    pma = "build/gawk-5.4.0-hybrid/c-residue/pma.o"
    if residues or digest(ROOT / pma) != release["source_library_sha256"][pma]:
        raise ValueError("GNU awk PMA object differs from the release")
    mapped, symbols = namespace_gawk_library(archive, stage)
    if symbols != release["gawk_namespaced_symbols"]:
        raise ValueError("GNU awk exports differ")
    return mapped, []


def commands(elf, work):
    proof = json.loads((ROOT / "evidence/gawk-errno-archive.json").read_bytes())["public"]
    programs = {cc: Path("/rustbox-gawk") / ("oracle-" + cc) / "gawk" for cc in ("gcc", "clang")}
    if {cc: digest(path) for cc, path in programs.items()} != proof["canonical"]:
        raise ValueError("GNU awk oracle executables differ")
    cases = {}
    for mode in ("applet", "subcommand"):
        folder = work / mode
        folder.mkdir()
        (folder / "extension").symlink_to(ROOT / "build/gawk-5.4.0-hybrid/extension")
        for name in ("awk", "gawk"):
            entry = folder / name
            if mode == "applet":
                entry.symlink_to(elf)
            else:
                entry.write_text("#!/bin/sh\nexec " + shlex.quote(str(elf)) + " " + name + ' "$@"\n')
                entry.chmod(0o755)
        for cc in ("gcc", "clang"):
            report = folder / (cc + ".json")
            subprocess.run([sys.executable, ROOT / "tests/gawk-oracle-differential.py",
                            "--gcc-build", programs[cc].parent, "--clang-build", folder, "--output", report],
                           check=True, stdout=subprocess.DEVNULL)
            result = json.loads(report.read_bytes())
            if result["cases"] != result["passed"] or result["passed"] != proof["public"][cc]:
                raise ValueError("GNU awk command suite differs")
            cases[mode + "-" + cc] = result["passed"]
        programs[mode] = folder / "gawk"
    # Exercise the awk alias as well, with the invocation name it receives.
    aliases = []
    for mode in ("applet", "subcommand"):
        proc = subprocess.run([work / mode / "awk", 'BEGIN { a["01"]=1; a[1]=2; print length(a), a["01"], a["1"] }'],
                              capture_output=True, timeout=30)
        if (proc.returncode, proc.stdout, proc.stderr) != (0, b"2 1 2\n", b""):
            raise ValueError("awk alias array keys differ")
        aliases.append(mode)
    # This corpus invokes binaries under the public name ./gawk.
    checks = gawk_keys.run(programs, work, subcommand=elf)
    old = json.loads((ROOT / "evidence/gawk-integer-key-baseline.json").read_bytes())
    if any(old[k] != v for k, v in checks.items()):
        raise ValueError("complete executable changed the array-key corpus")
    return dict(commands=cases, awk_alias=aliases, byte_keys=checks)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("parent", "log", "pilot", "output"):
        p.add_argument(arg, type=Path)
    a = p.parse_args()
    proof = json.loads((ROOT / "evidence/gawk-ctype-key-archive.json").read_bytes())["archive"]
    preview(a.parent, a.log, a.pilot, a.output, proof, namespace, commands)
