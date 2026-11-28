#!/usr/bin/env python3
"""Replay previously byte-identical leaf layout selections on a newer compiler snapshot."""
# SPDX-License-Identifier: 0BSD
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import json
from pathlib import Path
import subprocess
import sys
from tempfile import NamedTemporaryFile

from build_checked_errno import replay
from build_leaf_layout_pilot import build as cargo_build, substitute
from build_staged_c_strings import build as direct_build
from build_va_list_layout_batch import archive_folder
from cargo_source_parent import cargo_origin, direct_crate
from check_cargo_private_inlines import digest
from direct_source_pair import direct_receipt
from verify_c_string_sources import syntax_tool


def current_selection(layouts, key, previous):
    selected = {}
    for layout in layouts:
        name = layout["name"]
        if name not in previous or key not in layout["archives"]:
            continue
        if (name in selected or layout["declaration_and_field_types_sha256"] != previous[name]["fingerprint"]
                or layout["pointer_fields"] != previous[name]["pointer_fields"]):
            return None
        selected[name] = dict(fingerprint=previous[name]["fingerprint"], pointer_fields=layout["pointer_fields"],
                              copies=layout["archives"][key])
    return selected if selected.keys() == previous.keys() else None


def refresh(link, ranking, output, prior, jobs):
    release = json.loads(link.read_bytes())
    link_hash, rank_hash = digest(link), digest(ranking)
    ranked = json.loads(ranking.read_bytes())
    if ranked["link_report_sha256"] != link_hash or ranked["binary_sha256"] != release["binary"]["sha256"]:
        raise ValueError("layout ranking belongs to a different compiler selection")
    paths = {}
    for folder in prior:
        row = json.loads((folder/"pilot.json").read_bytes())
        key = row["archive"]
        if (key in paths or not row.get("leaf_layouts") or row["control_sha256"] != row["candidate_sha256"]
                or digest(folder/Path(key).name) != row["candidate_sha256"]):
            raise ValueError(f"expected a unique byte-identical layout pilot for {key}")
        paths[key] = (folder, row)
    output.mkdir(parents=True, exist_ok=True)
    scanner = syntax_tool("leaf-layouts")
    def inspect(key):
        old_dir, old = paths[key]
        if key not in release["source_library_sha256"]:
            return "deferred", {"reason":"archive path changed"}
        chosen = current_selection(ranked["layouts"], key, old["leaf_layouts"])
        if chosen is None:
            return "deferred", {"reason":"required layout missing, changed or ambiguous"}
        direct = direct_crate(cargo_origin(release, key)) is not None
        def change(crate, sources):
            return substitute(crate, sources, chosen, scanner=scanner)
        row = direct_receipt(link,key,change) if direct else replay(link,key,transform=change)
        if all(old.get(k) == v for k,v in row.items() if k != "control_binary_sha256"):
            # The same compiler inputs and identical emitted archive can serve another executable.
            folder, built = old_dir, old
        else:
            folder = archive_folder(output, key)
            with folder.with_suffix(".lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                if not folder.exists():
                    if direct:
                        direct_build(link,folder,key,leaf_layouts=chosen)
                    else:
                        cargo_build(link,key,chosen,folder)
                built = json.loads((folder/"pilot.json").read_bytes())
                if dict(row,candidate_sha256=digest(folder/Path(key).name)) != built:
                    raise ValueError(f"cold result differs from the current compiler replay for {key}")
        category = "identical" if built["control_sha256"] == built["candidate_sha256"] else "changed"
        return category, dict(directory=str(folder), receipt_sha256=digest(folder/"pilot.json"),
                              raw_pointer_types_removed=built["raw_pointer_types_removed"], reused=folder==old_dir)

    results = dict(link_sha256=link_hash, ranking_sha256=rank_hash, identical={}, changed={}, deferred={}, errors={})
    if not paths or jobs < 1:
        raise ValueError("expected at least one pilot and a positive worker count")
    # Try the largest previously qualified reduction first.
    ordered = sorted(paths, key=lambda k:-paths[k][1]["raw_pointer_types_removed"])
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        tasks = {pool.submit(inspect,k):k for k in ordered}
        for task in as_completed(tasks):
            key = tasks[task]
            try:
                category, item = task.result()
            except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as err:
                category, item = "errors", {"error": str(err)}
            if digest(link) != link_hash or digest(ranking) != rank_hash:
                raise ValueError("compiler selection or ranking changed during the refresh")
            results[category][key] = item
            with NamedTemporaryFile(mode="w", dir=output, delete=False) as f:
                json.dump(results, f, sort_keys=True, indent=2)
                f.write("\n")
            Path(f.name).replace(output/"results.json")
            print(f"{Path(key).name}: {category}", file=sys.stderr, flush=True)
    if results["errors"]:
        raise RuntimeError(f"inspect failed archive refreshes in {output / 'results.json'}")
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("link","ranking","output"):
        p.add_argument(name,type=Path)
    p.add_argument("prior",type=Path,nargs="+")
    p.add_argument("--jobs",type=int,default=1)
    a=p.parse_args()
    print(json.dumps(refresh(a.link,a.ranking,a.output,a.prior,a.jobs),indent=2,sort_keys=True))
