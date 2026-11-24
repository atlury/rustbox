#!/usr/bin/env python3
"""Group finalized Rust translations by exact contents for pointer-safety triage."""
# SPDX-License-Identifier: 0BSD

import argparse
import hashlib
import json
import re
from pathlib import Path

POINTER = re.compile(rb"\*(?:const|mut)\b")


def inventory(base):
    groups = {}
    crates = sorted(base.glob("*/*-final"))
    if not crates:
        raise ValueError(f"no finalized crates under {base}")
    for crate in crates:
        files = sorted(crate.rglob("*.rs"))
        if not files:
            raise ValueError(f"no Rust sources in {crate}")
        for path in files:
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if digest not in groups:
                groups[digest] = {
                    "sha256": digest,
                    "raw_pointer_tokens": len(POINTER.findall(data)),
                    "paths": [],
                }
            groups[digest]["paths"].append(str(path.relative_to(base)))

    repeated = []
    total = unique = 0
    for group in groups.values():
        pointers = group["raw_pointer_tokens"]
        copies = len(group["paths"])
        total += copies * pointers
        unique += pointers
        if copies > 1 and pointers:
            group["repeated_tokens"] = (copies - 1) * pointers
            repeated.append(group)
    return {
        "finalized_crates": len(crates),
        "files": sum(len(g["paths"]) for g in groups.values()),
        "distinct_files": len(groups),
        "raw_pointer_tokens": total,
        "tokens_counting_identical_files_once": unique,
        "duplicate_tokens": total - unique,
        "repeated_groups": sorted(repeated, key=lambda g: (-g["repeated_tokens"], g["sha256"])),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("translation_roots", nargs="+", type=Path,
                        help="program-translations directory containing finalized crates")
    args = parser.parse_args()
    print(json.dumps({str(base): inventory(base) for base in args.translation_roots}, indent=2))


if __name__ == "__main__":
    main()
