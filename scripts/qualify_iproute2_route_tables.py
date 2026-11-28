#!/usr/bin/env python3
"""Check each cold routing-table archive against its compiler projection and the two C oracles."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import fcntl
import json
from pathlib import Path
import subprocess
import sys

from build_iproute2_route_tables import build, substitute
from build_checked_errno import replay
from check_cargo_private_inlines import ROOT, digest
from direct_source_pair import direct_receipt
from link_rustbox_multicall import IPROUTE2_PROGRAMS
from qualify_iproute2_combined_names import write_result
from stage_dsfield_archives import FIELD, candidate_path, parent_view


def qualify(link, projection, standalone, output, engines):
    original = digest(link)
    release = json.loads(link.read_bytes())
    parent_view(release)
    rank = json.loads(projection.read_bytes())
    baseline = json.loads(standalone.read_bytes())
    expected = {str(candidate_path(row)) for row in release[FIELD].values()}
    if (rank["link_report_sha256"] != original or rank["binary_sha256"] != release["binary"]["sha256"]
            or rank["engines"].keys() != expected or baseline["oracle_compilers"] != ["gcc", "clang-18"]):
        raise ValueError("unexpected source projection or canonical reference")
    wanted = set(engines or IPROUTE2_PROGRAMS)
    output.mkdir(exist_ok=True)
    rows = {}
    for key, predicted in sorted(rank["engines"].items()):
        name = Path(key).name
        engine = name.removeprefix("lib").removesuffix("_audit.a")
        if engine not in wanted:
            continue
        trial = output / Path(key).stem
        receipt = output / (name + ".json")
        with (output / (name + ".lock")).open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not trial.exists():
                build(link, trial, key)
            archive = json.loads((trial / "pilot.json").read_bytes())
            facts = (direct_receipt(link, key, substitute) if "rustc_archive" in archive
                     else replay(link, key, transform=substitute))
            if dict(facts, candidate_sha256=digest(trial / name)) != archive:
                raise ValueError(f"{engine} archive differs from the source replay")
            for field, value in predicted.items():
                if field != "with_group_module_sha256" and archive["control_sha256" if field == "control_archive_sha256" else field] != value:
                    raise ValueError(f"{engine} compiler input differs in {field}")
            if receipt.is_file():
                result = json.loads(receipt.read_bytes())
            else:
                result = json.loads(subprocess.check_output([sys.executable, "-B", ROOT / "scripts/test_iproute2_route_tables.py",
                                                             "--link", link, "--pilot", trial]))
            fields = ("oracle_compilers", "memcheck_runs", "driver_sha256", "canonical_sha256", "helper_sha256")
            if (any(result[k] != v for k, v in archive.items()) or any(result[k] != baseline[k] for k in fields)
                    or [dict(p, public_statuses=[]) for p in result["profiles"]] != baseline["profiles"]
                    or any(len(p["public_statuses"]) != (9 if engine == "ip" else 0) for p in result["profiles"])):
                raise ValueError(f"{engine} canonical observations differ from the standalone reference")
            if not receipt.is_file():
                write_result(receipt, result)
            rows[key] = result
            print(f"{engine} passed both canonical compilers and Memcheck", flush=True)
    if len(rows) != len(wanted) or digest(link) != original:
        raise ValueError("incomplete selection or changed release report")
    if wanted == set(IPROUTE2_PROGRAMS):
        total = sum(r["raw_pointer_types_removed"] for r in rows.values())
        if total != rank["candidate_pointer_types"]:
            raise ValueError("full archive count differs from the projection")
        write_result(output / "combined-results.json", dict(verified=rows, binary_sha256=rank["binary_sha256"],
            link_sha256=original, raw_pointer_types_removed=total, source_projection_sha256=digest(projection),
            standalone_sha256=digest(standalone)))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("link", "projection", "standalone", "output"):
        p.add_argument(name, type=Path)
    p.add_argument("--engine", choices=IPROUTE2_PROGRAMS, action="append")
    args = p.parse_args()
    qualify(args.link, args.projection, args.standalone, args.output, args.engine)
