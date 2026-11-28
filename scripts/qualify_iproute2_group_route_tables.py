#!/usr/bin/env python3
"""Compare both owned name tables in one compiled IPRoute2 engine against canonical C."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import fcntl
import json
from pathlib import Path
import subprocess
import sys

from build_checked_errno import replay
from build_iproute2_group_route_tables import build, substitute
from check_cargo_private_inlines import ROOT, digest
from direct_source_pair import direct_receipt
from link_rustbox_multicall import IPROUTE2_PROGRAMS
from qualify_iproute2_combined_names import write_result
from stage_dsfield_archives import FIELD, candidate_path, parent_view


def qualify(link, engine, directory):
    link_hash = digest(link)
    release = json.loads(link.read_bytes())
    parent_view(release)
    key, = (str(path) for row in release[FIELD].values()
            if (path := candidate_path(row)).name == f"lib{engine}_audit.a")
    directory.mkdir(exist_ok=True)
    trial = directory / engine
    with (directory / (engine + ".lock")).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not trial.exists():
            build(link, key, trial)
        pilot = json.loads((trial / "pilot.json").read_bytes())
        facts = (direct_receipt(link, key, substitute) if "rustc_archive" in pilot else replay(link, key, transform=substitute))
        if dict(facts, candidate_sha256=digest(trial / Path(key).name)) != pilot:
            raise ValueError(f"{engine} differs from its joint compiler source replay")
        references = (("group", "test_group_names.py", "iproute2-group-names-pilot.json"),
                      ("route", "test_iproute2_route_tables.py", "iproute2-route-tables-standalone.json"))
        checks = {}
        for kind, driver, reference in references:
            baseline = json.loads((ROOT / "evidence" / reference).read_bytes())
            path = directory / f"{engine}-{kind}.json"
            observed = (json.loads(path.read_bytes()) if path.exists() else
                        json.loads(subprocess.check_output([sys.executable, "-B", ROOT / "scripts" / driver,
                                                            "--link", link, "--pilot", trial])))
            helper = pilot["group_helper_sha256" if kind == "group" else "helper_sha256"]
            expected = dict(pilot, helper_sha256=helper)
            if (any(observed[k] != v for k, v in expected.items()) or
                    any(observed[k] != baseline[k] for k in ("driver_sha256", "oracle_compilers", "memcheck_runs",
                                                             "canonical_sha256", "helper_sha256"))):
                raise ValueError(f"{engine} {kind} archive or canonical inputs changed")
            profiles = lambda report: [dict(profile, public_statuses=[]) for profile in report["profiles"]]
            if profiles(observed) != profiles(baseline):
                raise ValueError(f"{engine} {kind} lookup results differ from the canonical reference")
            if not path.exists():
                write_result(path, observed)
            checks[kind] = dict(report_sha256=digest(path), profiles=len(observed["profiles"]),
                                memcheck_runs=observed["memcheck_runs"], canonical_reference=reference)
        if digest(link) != link_hash:
            raise ValueError("link changed while checking the engine")
        result = dict(archive=pilot, link_sha256=link_hash, checks=checks)
        write_result(directory / (engine + ".json"), result)
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path)
    parser.add_argument("directory", type=Path)
    parser.add_argument("engine", choices=IPROUTE2_PROGRAMS)
    args = parser.parse_args()
    print(json.dumps(qualify(args.link, args.engine, args.directory), sort_keys=True, indent=2))
