#!/usr/bin/env python3
"""Check all five pkgconf entry points in the full Linux multicall after replacing byte classifiers."""
# SPDX-License-Identifier: ISC
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from check_cargo_private_inlines import ROOT, digest
from preview_cargo_multicall import preview_link

sys.path.insert(0, str(ROOT / "tests/ctype-values"))
from pkgconf_multicall import NAMES, entrypoints


def commands(elf, work):
    canonical = ROOT / "work/analysis/pkgconf-3.0.11/oracle"
    pins = json.loads((ROOT / "evidence/pkgconf-3.0.11-oracle.json").read_bytes())["binaries"]
    results = {}
    for cc in ("gcc", "clang"):
        folder = work / cc
        folder.mkdir()
        for name in NAMES:
            binary = ("pkgconf" if name == "pkg-config" else name) + "-" + cc
            if digest(canonical / binary) != pins[binary]["sha256"]:
                raise ValueError(f"unexpected canonical executable {binary}")
            (folder / name).symlink_to(canonical / binary)
    for mode in ("applet", "subcommand"):
        entrypoints(elf, work, mode)
        for cc in ("gcc", "clang"):
            report = work / f"{mode}-{cc}.json"
            subprocess.run([sys.executable, ROOT / "tests/pkgconf-differential.py", "--canonical-dir", work / cc,
                            "--hybrid-dir", work / mode, "--output", report], check=True, stdout=subprocess.DEVNULL)
            data = json.loads(report.read_bytes())
            if (not data["canonical_hybrid_exact"] or data["comparisons"] != len(data["records"])
                    or {r["tool"] for r in data["records"]} != set(NAMES)):
                raise ValueError("incomplete pkgconf command comparison")
            results[f"{mode}-{cc}"] = data["comparisons"]
    return dict(commands=results)


def run(parent, log, pilot, output):
    raw = parent.read_bytes()
    release = json.loads(raw)
    row = json.loads((pilot / "pilot.json").read_bytes())
    proof = json.loads((ROOT / "evidence/pkgconf-ctype-parser-archive.json").read_bytes())
    key = Path(row["archive"])
    if (key.is_absolute() or ".." in key.parts or row != proof["archive"]
            or release["source_library_sha256"].get(str(key)) != row["control_sha256"]):
        raise ValueError("pkgconf archive differs from the verified compiler inputs")

    def prepare(name, stage):
        original = name == "parent"
        path = ROOT / key if original else pilot / key.name
        archive = stage / key
        archive.parent.mkdir(parents=True)
        shutil.copyfile(path, archive)
        expected = row["control_sha256" if original else "candidate_sha256"]
        if digest(archive) != expected:
            raise ValueError(f"{name} pkgconf archive changed")
        return [archive], {archive}, dict(archive_sha256=expected)

    preview_link(parent, raw, log, output, prepare, commands, direct_archives=(key,))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("parent", "log", "pilot", "output"):
        p.add_argument(arg, type=Path)
    a = p.parse_args()
    run(a.parent, a.log, a.pilot, a.output)
