#!/usr/bin/env python3
"""Link enrolled declaration cleanups, replay changed packages and account for every removed pointer type."""
# SPDX-License-Identifier: 0BSD
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys

from check_cargo_private_inlines import LINK_REPORT, ROOT, digest
from test_inline_release import SENSITIVE, changed_packages
from verify_inline_replays import validate_replays, verify


def logged(command, log):
    with log.open("wb") as stream:
        subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=True)


def check(binary, directory, jobs, supplied_replays):
    before = LINK_REPORT.read_bytes()
    release = json.loads(before)
    if digest(binary) != release["binary"]["sha256"]:
        raise ValueError("snapshot differs from the current release executable")
    e2fs = json.loads((ROOT / "batches/e2fsprogs-foreign-declarations.json").read_bytes())
    cargo = json.loads((ROOT / "batches/multicall-cargo-foreign-declarations.json").read_bytes())
    if e2fs.keys() & cargo.keys():
        raise ValueError("duplicate declaration archive in release manifests")
    candidate = dict(release, linked_foreign_declaration_proofs={**e2fs, **cargo})
    packages = set(changed_packages(release, candidate))
    if not packages:
        raise ValueError("the manifests add no declaration changes to this release")
    directory.mkdir()
    previous, expected = directory / "previous.json", directory / "expected.json"
    previous.write_bytes(before)
    expected.write_text(json.dumps(candidate, indent=2, sort_keys=True) + "\n")
    scripts = ROOT / "scripts"

    def suite(group, folder):
        output = directory / folder
        command = [sys.executable, "-B", scripts / "test_inline_release.py", previous, expected,
                   binary, "--jobs", str(jobs), "--output", output]
        for package in sorted(group):
            command.extend(("--package", package))
        logged(command, directory / f"{folder}.log")
        return expected, output / "results.json"

    def inventory():
        with (directory / "inventory.json").open("wb") as out:
            subprocess.run([sys.executable, "-B", scripts / "audit_linked_pointers.py",
                            LINK_REPORT, "--verify-cleanup-from", previous], cwd=ROOT, stdout=out, check=True)

    replays = list(supplied_replays)
    checked, _ = validate_replays(previous, expected, replays)
    pending = packages - checked["passing_package_selections"].keys()
    with ThreadPoolExecutor(max_workers=2) as workers:
        independent = pending - SENSITIVE
        early = workers.submit(suite, independent, "independent-tests") if independent else None
        logged([scripts / "build_rustbox_multicall.sh"], directory / "build.log")
        if LINK_REPORT.read_bytes() != expected.read_bytes():
            raise ValueError("production link differs from the exact expected release")
        audit = workers.submit(inventory)
        if early:
            replays.append(early.result())
        audit.result()
    if sensitive := pending & SENSITIVE:
        replays.append(suite(sensitive, "sensitive-tests"))
    (directory / "replays.json").write_text(json.dumps(verify(previous, LINK_REPORT, replays),
                                                      sort_keys=True, indent=2) + "\n")
    logged([scripts / "test_rustbox_multicall.sh"], directory / "dispatch.log")
    if "iproute2" in packages:
        logged([scripts / "test_iproute2_rtattr.sh", "--multicall"], directory / "iproute2-live.log")
    if "e2fsprogs" in packages:
        for test in ("bitcount", "crc16"):
            logged([scripts / f"test_e2fsprogs_{test}.sh", "--multicall"], directory / f"e2fsprogs-{test}.log")
    for family in ("inetutils", "e2fsprogs", "iproute2", "curl", "rustbox"):
        logged([scripts / f"summarize_{family}_multicall.sh"], directory / f"summary-{family}.log")
    if LINK_REPORT.read_bytes() != expected.read_bytes():
        raise ValueError("release changed during the final checks")
    print(f"Verified {len(packages)} package suites and the linked inventory in {directory}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path, help="saved unstripped Linux multicall")
    parser.add_argument("directory", type=Path, help="new output directory")
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--replay", nargs=2, type=Path, action="append", default=[], metavar=("SELECTION", "RESULTS"),
                        help="reuse a completed package replay after checking it against the expected release")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    check(args.binary.resolve(), args.directory.resolve(), args.jobs, args.replay)
