#!/usr/bin/env python3
"""Check that package replays on partial selections cover the exact final cleanup release."""
# SPDX-License-Identifier: 0BSD
import argparse
import hashlib
import json
from pathlib import Path

from test_inline_release import changed_packages


def verify(previous_path, final_path, replays):
    before = previous_path.read_bytes()
    previous_sha = hashlib.sha256(before).hexdigest()
    previous = json.loads(before)
    final_bytes = final_path.read_bytes()
    final = json.loads(final_bytes)
    required = set(changed_packages(previous, final))
    binary_sha = final["binary"]["sha256"]
    passed = {}
    for selection, result_path in replays:
        data = selection.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        partial = json.loads(data)
        result = json.loads(result_path.read_bytes())
        if (result["previous_link_report_sha256"] != previous_sha or result["binary_sha256"] != binary_sha
                or result["link_report_sha256"] != sha):
            raise ValueError(f"replay evidence belongs to a different release: {result_path}")
        # Both comparisons retain every earlier receipt and check every non-receipt link field.
        covered = set(changed_packages(previous, partial)) - set(changed_packages(partial, final))
        for package, status in result["statuses"].items():
            if package not in covered or type(status) is not int or status != 0:
                raise ValueError(f"incomplete {package} replay in {result_path}")
            passed[package] = sha
    if passed.keys() != required:
        raise ValueError(f"missing completed replays for {sorted(required - passed.keys())}")
    return {"binary_sha256": binary_sha, "previous_link_report_sha256": previous_sha,
            "link_report_sha256": hashlib.sha256(final_bytes).hexdigest(), "passing_package_selections": passed}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("previous", type=Path)
    parser.add_argument("release", type=Path)
    parser.add_argument("--replay", nargs=2, type=Path, action="append", required=True,
                        metavar=("SELECTION", "RESULTS"))
    args = parser.parse_args()
    print(json.dumps(verify(args.previous, args.release, args.replay), sort_keys=True, indent=2))
