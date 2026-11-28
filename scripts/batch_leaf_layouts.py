#!/usr/bin/env python3
"""Cold-build repeated leaf layouts by archive and recount only byte-identical, independently replayed groups."""
# SPDX-License-Identifier: 0BSD
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import json
from pathlib import Path
import subprocess
import sys
from tempfile import NamedTemporaryFile

from build_va_list_layout_batch import archive_folder
from cargo_source_parent import cargo_origin, direct_crate
from check_cargo_private_inlines import ROOT, digest


def run(link, ranking, output, exclude_layouts, exclude_packages, jobs):
    script = ROOT / "scripts/build_leaf_layout_pilot.py"
    scanner = ROOT / "tools/private-inlines/src/bin/leaf-layouts.rs"
    parent, rank = (json.loads(path.read_bytes()) for path in (link, ranking))
    inputs = dict(link_sha256=link, ranking_sha256=ranking, scanner_sha256=scanner, selector_sha256=script,
                  ranking_script_sha256=ROOT / "scripts/rank_leaf_c_layouts.py")
    stamp = {name: digest(path) for name, path in inputs.items()}
    stamp.update(exclude_layouts=sorted(exclude_layouts), exclude_packages=sorted(exclude_packages))
    if stamp["link_sha256"] != rank["link_report_sha256"] or rank["binary_sha256"] != parent["binary"]["sha256"]:
        raise ValueError("ranking differs from the selected release")

    options = defaultdict(lambda: defaultdict(list))
    for row in rank["layouts"]:
        name = row["name"]
        if name in exclude_layouts:
            continue
        for key, n in row["archives"].items():
            if Path(key).parts[2] not in exclude_packages:
                options[key][name].append(row["pointer_fields"] * (n - 1))

    selected, skipped = {}, {}
    for key, names in options.items():
        if direct_crate(cargo_origin(parent, key)) is not None:
            skipped[key] = "archive uses direct rustc"
            continue
        single = {name: counts[0] for name, counts in names.items() if len(counts) == 1}
        if len(single) != len(names):
            skipped[key] = {"ambiguous_layouts": sorted(set(names) - set(single))}
        if single:
            selected[key] = single
    if not selected:
        raise ValueError("no eligible Cargo archives in the selection")

    def check(key):
        folder = archive_folder(output, key)
        layouts = sorted(selected[key])
        cmd = [sys.executable, "-B", script, "--link", link, "--ranking", ranking, "--archive", key,
               "--layouts", *layouts, "--output", folder]
        with folder.with_suffix(".log").open("ab") as log:
            if not folder.exists():
                subprocess.run(cmd, check=True, stdout=log, stderr=subprocess.STDOUT)
            subprocess.run([*cmd, "--replay"], check=True, stdout=log, stderr=subprocess.STDOUT)
        row = json.loads((folder / "pilot.json").read_bytes())
        if (row["archive"] != key or set(row["leaf_layouts"]) != set(layouts)
                or row["raw_pointer_types_removed"] != sum(selected[key].values())
                or row["control_sha256"] != parent["source_library_sha256"][key]):
            raise ValueError("replayed compiler receipt differs from ranked groups")
        category = "identical" if row["candidate_sha256"] == row["control_sha256"] else "changed"
        return category, dict(pilot_sha256=digest(folder / "pilot.json"), archive_sha256=row["candidate_sha256"],
                              raw_pointer_types_removed=row["raw_pointer_types_removed"], layouts=layouts)

    output.mkdir(parents=True, exist_ok=True)
    summary = output / "results.json"
    request = output / "selection.json"
    with (output / "batch.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if request.exists() and json.loads(request.read_bytes()) != stamp:
            raise ValueError("output already belongs to a different source selection")
        if not request.exists():
            if any(path.name != "batch.lock" for path in output.iterdir()):
                raise ValueError("unidentified files in batch output")
            request.write_text(json.dumps(stamp, indent=2, sort_keys=True) + "\n")
        report = dict(**stamp, selected=len(selected), skipped=skipped, identical={}, changed={}, errors={})
        if summary.exists():
            previous = json.loads(summary.read_bytes())
            if any(previous.get(field) != value for field, value in stamp.items()):
                raise ValueError("saved results do not describe this source selection")
            for category in ("identical", "changed", "errors"):
                if set(previous[category]) - set(selected):
                    raise ValueError("saved results contain an unselected archive")
                report[category] = previous[category]
        ordered = sorted(selected, key=lambda key: (-sum(selected[key].values()), key))
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = {pool.submit(check, key): key for key in ordered}
            for future in as_completed(futures):
                key = futures[future]
                try:
                    category, result = future.result()
                except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
                    category, result = "errors", str(exc)
                for prior in ("identical", "changed", "errors"):
                    report[prior].pop(key, None)
                report[category][key] = result
                report["verified_pointer_types_removed"] = sum(row["raw_pointer_types_removed"] for row in report["identical"].values())
                if any(digest(path) != stamp[name] for name, path in inputs.items()):
                    raise ValueError("a source release, ranking or selector changed during the batch")
                with NamedTemporaryFile(mode="w", dir=output, delete=False) as staged:
                    json.dump(report, staged, indent=2, sort_keys=True)
                    staged.write("\n")
                Path(staged.name).replace(summary)
                print(Path(key).name, category, report["verified_pointer_types_removed"], flush=True)
    return not report["errors"]


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("link", "ranking", "output"):
        p.add_argument(arg, type=Path)
    p.add_argument("--exclude-layout", action="append", default=[])
    p.add_argument("--exclude-package", action="append", default=[])
    p.add_argument("--jobs", type=int, default=1)
    args = p.parse_args()
    if args.jobs < 1:
        p.error("--jobs must be positive")
    sys.exit(0 if run(args.link, args.ranking, args.output, args.exclude_layout, args.exclude_package, args.jobs) else 1)
