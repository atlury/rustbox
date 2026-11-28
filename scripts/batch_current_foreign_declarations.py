#!/usr/bin/env python3
"""Cold-build and replay current Cargo foreign-declaration candidates in descending estimated impact."""
# SPDX-License-Identifier: 0BSD
import argparse
import fcntl
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

from cargo_source_parent import cargo_origin, direct_crate
from check_cargo_private_inlines import ROOT, digest, layout
from qualify_iproute2_combined_names import write_result
from rank_foreign_declarations import rank


def run(link, directory):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ranking = directory / "ranking.json"
        if not ranking.exists():
            write_result(ranking, rank(link))
        ranked = json.loads(ranking.read_bytes())
        release = json.loads(link.read_bytes())
        if digest(link) != ranked["link_report_sha256"] or ranked["binary_sha256"] != release["binary"]["sha256"]:
            raise ValueError("resume requires the same release and ranking")
        results = {}
        for entry in ranked["archives"]:
            key = entry["archive"]
            if not entry["candidate_pointer_types"]:
                continue
            origin = cargo_origin(release, key)
            if direct_crate(origin) is not None:
                continue
            try:
                layout(origin)
            except ValueError:
                continue
            identifier = Path(key).stem + "-" + sha256(key.encode()).hexdigest()[:12]
            stage = directory / identifier
            cmd = [sys.executable, "-B", ROOT / "scripts/build_current_foreign_declarations.py",
                   "--link", link, "--archive", key, "--output", stage]
            with (directory / (identifier + ".log")).open("ab") as log:
                process = subprocess.run(cmd + (["--replay"] if stage.is_dir() else []), stdout=log, stderr=log)
            if process.returncode:
                results[key] = dict(status="unqualified", log=identifier+".log")
            else:
                row = json.loads((stage / "pilot.json").read_bytes())
                results[key] = dict(status="archive-identical" if row["candidate_sha256"] == row["control_sha256"]
                                    else "requires-relink", receipt_sha256=digest(stage / "pilot.json"),
                                    raw_pointer_types_removed=row["raw_pointer_types_removed"], directory=identifier)
            if digest(link) != ranked["link_report_sha256"]:
                raise ValueError("release changed during the sweep")
            write_result(directory / "results.json", dict(link_sha256=ranked["link_report_sha256"], archives=results))
            print(Path(key).name, results[key]["status"], results[key].get("raw_pointer_types_removed", 0), flush=True)
        return int(any(r["status"] == "unqualified" for r in results.values()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    raise SystemExit(run(args.link, args.directory))
