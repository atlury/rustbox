#!/usr/bin/env python3
"""Run one checked errno archive through its canonical Linux tests and independent source replay."""
# SPDX-License-Identifier: 0BSD
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

from build_checked_errno import replay
from check_cargo_private_inlines import ROOT

VERSIONS = {"sed": "4.10", "grep": "3.12", "gzip": "1.14", "shadow": "4.20.4", "findutils": "4.10.0"}


def checked(package, link, pilot, *, build):
    original = link.read_bytes()
    parent = json.loads(original)
    key, = [k for k in parent["source_library_sha256"]
            if Path(k).name.startswith("lib" + package + "_") and k.endswith(".a")]
    # The existing candidate is checked against the specified parent, including all compiler inputs.
    if build and not pilot.exists():
        subprocess.run([sys.executable, "-B", ROOT / "scripts/build_checked_errno.py", "--link", link,
                        "--archive", key, "--output", pilot], stdout=sys.stderr, check=True)
    row = replay(link, key, pilot)
    version = VERSIONS[package]
    docker = ["docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64",
              "-v", f"{ROOT}:/work:ro", "-v", f"rustbox-{package}-{version}:/rustbox-{package}:ro",
              "-w", "/work", "rustbox-e2fsprogs:2026-11-24", "python3", "-B"]
    public = package in ("findutils", "shadow")
    if public:
        script = ["tests/errno-values/command-archives.py", package]
    elif package == "sed":
        script = ["tests/errno-values/sed.py"]
    else:
        script = ["tests/errno-values/descriptors.py", package]
    arg = str(link.resolve().relative_to(ROOT))
    def compare(extra):
        return json.loads(subprocess.check_output([*docker, *script, arg, *extra]))
    baseline = compare([])
    flags = ["--memcheck"] if public else []
    candidate = compare([str(pilot.resolve().relative_to(ROOT)), *flags])
    if public:
        if (baseline["public"] != candidate["public"] or baseline["archive_sha256"] != row["control_sha256"]
                or candidate["archive_sha256"] != row["candidate_sha256"] or candidate["memcheck_runs"] != 6):
            raise ValueError("command or memory results differ on the specified archives")
    else:
        archives = dict(baseline["archive_sha256"], candidate=row["candidate_sha256"])
        if (baseline["archive_sha256"]["parent"] != row["control_sha256"] or candidate["archive_sha256"] != archives
                or not baseline["api_outputs"].items() <= candidate["api_outputs"].items()
                or len(candidate["api_outputs"]) != 8 or len(set(candidate["api_outputs"].values())) != 1
                or not candidate["public_commands"]["gcc"] or candidate["public_commands"]["gcc"] != candidate["public_commands"]["clang"]):
            raise ValueError("archive, command or API comparisons differ")
    if link.read_bytes() != original:
        raise ValueError("selection changed during command checks")
    return dict(link_report_sha256=sha256(original).hexdigest(), archive=row, baseline=baseline, candidate=candidate)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("package", choices=VERSIONS)
    p.add_argument("link", type=Path)
    p.add_argument("pilot", type=Path)
    p.add_argument("--build", action="store_true", help="cold-build the candidate if the directory does not exist")
    a = p.parse_args()
    print(json.dumps(checked(a.package, a.link, a.pilot, build=a.build), sort_keys=True, indent=2))
