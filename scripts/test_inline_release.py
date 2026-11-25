#!/usr/bin/env python3
"""Run existing package suites for added cleanup receipts against the exact linked Linux binary."""
# SPDX-License-Identifier: 0BSD
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from audit_linked_pointers import added_receipts
from check_cargo_private_inlines import ROOT, digest

# These canonical suites measure wall-clock time, process state, or pipe scheduling.
SENSITIVE = {"diffutils", "gawk", "procps-ng", "shadow"}


def all_packages():
    scripts = (ROOT / "scripts").glob("test_*_multicall.sh")
    names = {script.stem.removeprefix("test_").removesuffix("_multicall") for script in scripts}
    names.remove("rustbox")  # The aggregate dispatcher is a separate gate.
    return {"procps-ng" if name == "procps" else name for name in names}


def changed_packages(before, after):
    return sorted({re.sub(r"-[0-9].*$", "", Path(path).relative_to("work/analysis").parts[0])
                   for path in added_receipts(before, after)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("previous", type=Path)
    parser.add_argument("release", type=Path)
    parser.add_argument("binary", type=Path, help="host path to the unstripped Linux executable")
    parser.add_argument("--all-packages", action="store_true",
                        help="test the new executable across all registered package suites after a live-code change")
    parser.add_argument("--package", action="append", help="run only this selected package (repeatable)")
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--output", type=Path, help="new directory for logs and the verified result")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    before_data = args.previous.read_bytes()
    release_data = args.release.read_bytes()
    release = json.loads(release_data)
    if args.all_packages:
        packages = sorted(all_packages())
    else:
        packages = changed_packages(json.loads(before_data), release)
    if args.package:
        if set(args.package) - set(packages):
            parser.error("requested package is outside the selected suites")
        packages = sorted(set(args.package))
    binary = args.binary.resolve()
    sha = release["binary"]["sha256"]
    if digest(binary) != sha:
        parser.error("test executable differs from the release")
    if not packages:
        print("The release has no added package receipts.")
        return 0
    if args.output:
        directory = args.output.resolve()
        directory.mkdir()
    else:
        directory = Path(tempfile.mkdtemp(prefix="inline-release-tests-", dir=ROOT / "work/analysis"))
    print(f"Testing {len(packages)} packages on {sha}, logs in {directory}", flush=True)
    environment = dict(os.environ, RUSTBOX_MULTICALL_TEST_BINARY=str(binary))

    def test(package):
        name = "procps" if package == "procps-ng" else package
        script = ROOT / f"scripts/test_{name}_multicall.sh"
        with (directory / f"{package}.log").open("wb") as log:
            command = subprocess.run([script], cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
        print(f"{package}: exit {command.returncode}", flush=True)
        return package, command.returncode

    with ThreadPoolExecutor(max_workers=args.jobs) as workers:
        statuses = dict(workers.map(test, [p for p in packages if p not in SENSITIVE]))
    statuses.update(test(p) for p in packages if p in SENSITIVE)
    if digest(binary) != sha:
        raise ValueError("test binary changed during the suite")
    if args.release.read_bytes() != release_data or args.previous.read_bytes() != before_data:
        raise ValueError("link report changed during the suite")
    (directory / "results.json").write_text(json.dumps(
        {"binary_sha256": sha, "previous_link_report_sha256": hashlib.sha256(before_data).hexdigest(),
         "link_report_sha256": hashlib.sha256(release_data).hexdigest(), "statuses": statuses},
        indent=2, sort_keys=True) + "\n")
    return int(any(statuses.values()))


if __name__ == "__main__":
    raise SystemExit(main())
