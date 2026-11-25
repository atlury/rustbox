#!/usr/bin/env python3
"""Verify an array-hardened multicall against its control release and all local package suites."""
# SPDX-License-Identifier: GPL-2.0-only
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from check_cargo_private_inlines import ROOT, LINK_REPORT, digest
from test_inline_release import SENSITIVE, all_packages
from verify_declaration_release import logged


def verify(before, binary, output, jobs, independent_replay=None):
    selected = LINK_REPORT.read_bytes()
    release = json.loads(selected)
    if digest(binary) != release["binary"]["sha256"]:
        raise ValueError("test executable differs from the linked directory hash release")
    output.mkdir()
    current = output / "release.json"
    current.write_bytes(selected)
    previous = output / "control.json"
    previous.write_bytes(before.read_bytes())
    scripts = ROOT / "scripts"

    def packages(names, folder):
        if folder == "independent" and independent_replay:
            result = json.loads(independent_replay.read_bytes())
        else:
            command = [sys.executable, "-B", scripts / "test_inline_release.py", previous, current, binary,
                       "--all-packages", "--jobs", str(jobs), "--output", output / folder]
            for name in sorted(names):
                command.extend(["--package", name])
            logged(command, output / f"{folder}.log")
            result = json.loads((output / folder / "results.json").read_bytes())
        statuses = result["statuses"]
        if (set(statuses) != names or any(type(code) is not int or code != 0 for code in statuses.values())
                or result["binary_sha256"] != digest(binary)
                or result["link_report_sha256"] != digest(current)
                or result["previous_link_report_sha256"] != digest(previous)):
            raise ValueError(f"package coverage differs for {folder}")
        return statuses

    tasks = [
        ("dispatcher", ["test_rustbox_multicall.sh"]),
        ("batch-differential", ["test_rustbox_batch_differential.sh"]),
        ("iproute2-live", ["test_iproute2_rtattr.sh", "--multicall"]),
        ("e2fsprogs-dirhash", ["test_e2fsprogs_dirhash_arrays.sh", "--multicall"]),
        ("e2fsprogs-bitcount", ["test_e2fsprogs_bitcount.sh", "--multicall"]),
        ("e2fsprogs-crc16", ["test_e2fsprogs_crc16.sh", "--multicall"]),
    ]
    inventory = output / "inventory.json"
    with inventory.open("wb") as stream:
        subprocess.run([sys.executable, "-B", scripts / "audit_linked_pointers.py", current,
                        "--verify-dirhash-from", previous], cwd=ROOT, stdout=stream, check=True)
    registered = all_packages()
    with ThreadPoolExecutor(max_workers=1) as worker:
        independent = worker.submit(packages, registered - SENSITIVE, "independent")
        for name, (tool, *args) in tasks:
            logged([scripts / tool, *args], output / f"{name}.log")
            print(f"{name} passed", flush=True)
        statuses = independent.result()
    statuses.update(packages(registered & SENSITIVE, "sensitive"))
    for family in ("inetutils", "e2fsprogs", "iproute2", "curl", "rustbox"):
        logged([scripts / f"summarize_{family}_multicall.sh"], output / f"summary-{family}.log")
    if LINK_REPORT.read_bytes() != selected or digest(binary) != release["binary"]["sha256"]:
        raise ValueError("release changed during verification")
    result = {"link_report_sha256": hashlib.sha256(selected).hexdigest(), "previous_link_report_sha256": digest(previous),
              "binary_sha256": release["binary"]["sha256"], "packages": statuses, "passed_checks": [name for name, _ in tasks]}
    (output / "replays.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(f"Verified the directory hash conversion and {len(registered)} package suites", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("previous", type=Path, help="saved link report from before the live conversion")
    parser.add_argument("binary", type=Path, help="saved copy of the newly linked Linux ELF")
    parser.add_argument("output", type=Path, help="new results directory")
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--independent-replay", type=Path,
                        help="verified results from all independent packages for this exact release and control")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    verify(args.previous.resolve(), args.binary.resolve(), args.output.resolve(), args.jobs, args.independent_replay)
