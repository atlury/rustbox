#!/usr/bin/env python3
"""Cold-build device-group rewrites on an optimized selection and reuse exact earlier compiler inputs."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import fcntl
import json
from pathlib import Path

from build_group_names import build
from check_cargo_private_inlines import ROOT, digest
from link_rustbox_multicall import IPROUTE2_PROGRAMS
from qualify_iproute2_combined_names import write_result
from rebase_iproute2_group_names import verify
from stage_dsfield_archives import FIELD, candidate_path, parent_view


def qualify(link, projection, output, shared=None, engines=None):
    original = digest(link)
    release = json.loads(link.read_bytes())
    parent_view(release)
    rank = json.loads(projection.read_bytes())
    selected = {str(candidate_path(row)): row for row in release[FIELD].values()}
    if (original != rank["link_report_sha256"] or release["binary"]["sha256"] != rank["binary_sha256"]
            or selected.keys() != rank["engines"].keys()):
        raise ValueError("group-name projection belongs to different compiler inputs")
    filters = set(engines or IPROUTE2_PROGRAMS)
    if not filters or filters - set(IPROUTE2_PROGRAMS):
        raise ValueError("unknown IPRoute2 engine")
    output.mkdir(exist_ok=True)
    results = {}
    for key, prior in sorted(selected.items()):
        name = Path(key).name
        engine = name.removeprefix("lib").removesuffix("_audit.a")
        if engine not in filters:
            continue
        expected = rank["engines"][key]
        parent_matches = prior["candidate_sources_sha256"] == expected["parent_sources_sha256"]
        base = shared if shared and parent_matches else output
        base.mkdir(exist_ok=True)
        trial = base / Path(key).stem
        with (base / (trial.name + ".lock")).open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not trial.exists():
                build(link, trial, key)
            row = json.loads((trial / "pilot.json").read_bytes())
            for field, value in expected.items():
                if row["control_sha256" if field == "control_archive_sha256" else field] != value:
                    raise ValueError(f"cold-built {engine} differs from projected {field}")
            receipt = output / (name + ".json")
            history = ROOT / "evidence" / f"iproute2-{engine}-combined-name-tables.json"
            if not history.is_file():
                history = shared / trial.name / "combined-comparison.json" if shared else None
            evidence = history if history and history.is_file() else None
            if receipt.exists():
                checked = json.loads(receipt.read_bytes())
                if (checked["archive"] != row or checked["link_sha256"] != original
                        or digest(trial / name) != row["candidate_sha256"]):
                    raise ValueError(f"saved {engine} result differs from linked compiler inputs")
            else:
                checked = verify(link, trial, evidence)
                write_result(receipt, checked)
            results[key] = checked
            print(f"{engine}: {row['raw_pointer_types_removed']} source occurrences removed", flush=True)
    if digest(link) != original or len(results) != len(filters):
        raise ValueError("incomplete selection or changed link")
    if filters == set(IPROUTE2_PROGRAMS):
        total = sum(r["archive"]["raw_pointer_types_removed"] for r in results.values())
        if total != rank["candidate_pointer_types"]:
            raise ValueError("compiler receipts differ from full source projection")
        write_result(output / "combined-results.json", dict(verified=results, link_sha256=original,
                     binary_sha256=rank["binary_sha256"], projection_sha256=digest(projection),
                     raw_pointer_types_removed=total))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("link", "projection", "output"):
        p.add_argument(name, type=Path)
    p.add_argument("--shared", type=Path, help="cold builds on the original DS-field selection")
    p.add_argument("--engine", action="append", choices=IPROUTE2_PROGRAMS)
    args = p.parse_args()
    qualify(args.link, args.projection, args.output, args.shared, args.engine)
