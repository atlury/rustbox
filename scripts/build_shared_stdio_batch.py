#!/usr/bin/env python3
"""Cold-build ranked Cargo archives and retain receipts only when sharing FILE preserves all bytes."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from check_cargo_private_inlines import ROOT, digest, layout


def run(link_file, ranks, output, packages, jobs):
    raw = link_file.read_bytes()
    link = json.loads(raw)
    ranking = json.loads(ranks.read_bytes())
    if (ranking["binary_sha256"] != link["binary"]["sha256"]
            or ranking["link_report_sha256"] != hashlib.sha256(raw).hexdigest()):
        raise ValueError("the layout ranking belongs to a different link")
    output.mkdir(parents=True, exist_ok=True)
    rows = {row["archive"]: row for row in ranking["archives"]}
    if len(rows) != len(ranking["archives"]):
        raise ValueError("duplicate ranked archive")
    selected = {k: r for k, r in rows.items() if not packages or Path(k).parts[2] in packages}
    if not selected or set(packages) - {Path(k).parts[2] for k in selected}:
        raise ValueError("empty batch or unknown package selection")

    def qualify(item):
        key, ranked = item
        archive = Path(key)
        control = link["source_library_sha256"][key]
        try:
            src, _ = layout(archive)
        except ValueError:
            return key, None, "requires its package-specific staged build"
        if not (ROOT / src / "rust-toolchain.toml").is_file():
            return key, None, "missing a pinned Cargo compiler for this archive"
        # Distinguish equal archive filenames from separate packages or build paths.
        tag = archive.stem + "-" + hashlib.sha256(key.encode()).hexdigest()[:12]
        result = output / tag
        if not result.exists():
            with (output / (tag + ".log")).open("wb") as log:
                built = subprocess.run([sys.executable, "-B", ROOT / "scripts/build_shared_stdio_pilot.py",
                                        "--link", link_file, "--archive", archive, "--output", result],
                                       stdout=log, stderr=subprocess.STDOUT)
            if built.returncode:
                return key, None, f"cold build failed, see {tag}.log"
        row = json.loads((result / "pilot.json").read_bytes())
        copied = row["reexporting_modules"]
        if (row["archive"] != key or row["control_binary_sha256"] != link["binary"]["sha256"]
                or row["control_sha256"] != control or digest(ROOT / archive) != control
                or row["candidate_sha256"] != digest(result / archive.name)
                or row["raw_pointer_types_removed"] != ranked["repeated_pointer_fields"]
                or len(set(copied)) != len(copied) or row["provider"] in copied
                or len(copied) + 1 != ranked["modules"]):
            raise ValueError(f"stale or incomplete layout receipt for {key}")
        if row["candidate_sha256"] != control:
            return key, None, "rebuilt archive bytes differ"
        return key, row, None

    passed, deferred = {}, {}
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        for key, row, reason in pool.map(qualify, selected.items()):
            if reason:
                deferred[key] = reason
                print(Path(key).name, reason, flush=True)
            else:
                passed[key] = row
                print(Path(key).name, "matched", row["raw_pointer_types_removed"], flush=True)
    if link_file.read_bytes() != raw:
        raise ValueError("release changed during the batch")
    summary = dict(binary_sha256=ranking["binary_sha256"], link_report_sha256=ranking["link_report_sha256"],
                   verified=passed, deferred=deferred, raw_pointer_types_removed=sum(r["raw_pointer_types_removed"] for r in passed.values()))
    staged = output / "results.json.tmp"
    staged.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    staged.replace(output / "results.json")
    print(f"{len(passed)} archives matched their original bytes; {len(deferred)} deferred", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path)
    parser.add_argument("ranks", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--package", action="append", default=[], help="package/version from the ranking, repeatable")
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    run(args.link.resolve(), args.ranks, args.output.resolve(), args.package, args.jobs)
