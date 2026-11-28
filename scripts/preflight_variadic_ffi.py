#!/usr/bin/env python3
"""Replay shared variadic declarations on each ranked archive's actual compiler inputs."""
# SPDX-License-Identifier: 0BSD
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

from build_checked_errno import replay
from build_scalar_ffi import SOURCE
from build_variadic_ffi import SELECTOR, substitute
from check_cargo_private_inlines import digest


def preflight(link, ranking, jobs):
    source_hash, rank_hash = digest(link), digest(ranking)
    ranked = json.loads(ranking.read_bytes())
    if (ranked["link_sha256"] != source_hash or ranked["scanner_source_sha256"] != digest(SOURCE)
            or ranked["variadic_scanner_sha256"] != digest(SELECTOR) or jobs < 1):
        raise ValueError("expected a current variadic ranking and a positive worker count")
    def inspect(key):
        receipt = replay(link, key, transform=substitute)
        removed = receipt["raw_pointer_types_removed"]
        if receipt["control_binary_sha256"] != ranked["binary_sha256"] or not 0 < removed <= ranked["archives"][key]:
            raise ValueError(f"compiler inputs differ from the ranking for {key}")
        return key, dict(archive=key, removed=removed, parent=receipt["parent_sources_sha256"],
                         candidate=receipt["candidate_sources_sha256"])
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        rows = dict(pool.map(inspect, sorted(ranked["archives"])))
    if source_hash != digest(link) or rank_hash != digest(ranking):
        raise ValueError("release or ranking changed during the replay")
    return dict(link_sha256=source_hash, rank_sha256=rank_hash, total=sum(row["removed"] for row in rows.values()), rows=rows)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("link", type=Path)
    p.add_argument("ranking", type=Path)
    p.add_argument("--jobs", type=int, default=2)
    args = p.parse_args()
    print(json.dumps(preflight(args.link, args.ranking, args.jobs), sort_keys=True, indent=2))
