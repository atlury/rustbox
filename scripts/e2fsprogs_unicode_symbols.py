#!/usr/bin/env python3
"""Measure strong-symbol changes directly in the independently rebuilt Unicode archives."""
# SPDX-License-Identifier: GPL-2.0-only
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import subprocess

from check_cargo_private_inlines import digest
from e2fsprogs_dirhash_archives import candidate_path, prior_stage


def symbols(path):
    rows = subprocess.check_output(["nm", "-g", "--defined-only", path], text=True, stderr=subprocess.DEVNULL)
    return {fields[-1] for row in rows.splitlines() if len(fields := row.split()) >= 3
            and fields[-2] in {"B", "C", "D", "G", "R", "S", "T"}
            and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", fields[-1])}


def measure(manifest, stage):
    records = json.loads(manifest.read_bytes())

    def compare(item):
        key, row = item
        base = Path(key)
        parent = prior_stage(row, stage)
        old = candidate_path(base, parent["candidate_sha256"])
        new = candidate_path(base, row["candidate_sha256"])
        if digest(old) != parent["candidate_sha256"] or digest(new) != row["candidate_sha256"]:
            raise ValueError(f"{base.parent.name} differs from its pinned archive")
        before, after = symbols(old), symbols(new)
        return base.parent.name, {"before": parent["candidate_sha256"], "after": row["candidate_sha256"],
                                  "added": sorted(after - before), "removed": sorted(before - after)}

    with ThreadPoolExecutor(max_workers=4) as workers:
        return dict(workers.map(compare, records.items()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("stage", choices=("hangul", "trie"))
    args = parser.parse_args()
    print(json.dumps(measure(args.manifest, args.stage), sort_keys=True, indent=2))
