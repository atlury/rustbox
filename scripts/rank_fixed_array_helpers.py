#!/usr/bin/env python3
"""Rank generated private helpers whose pointer parameters have only constant-offset uses."""
# SPDX-License-Identifier: 0BSD
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from audit_linked_pointers import measure
from batch_cargo_private_inlines import IDENTIFIER

# Deliberately limited to plain top-level functions in the C2Rust output format.
FUNCTION = re.compile(rb'^unsafe extern "C" fn (\w+)\(([^(){}]*)\)\s*(?:-> [^{}]+?)?\{\n(.*?)^\}', re.M | re.S)
ARGUMENT = re.compile(rb'\s*(?:mut )?(\w+):\s*(?:(\*mut|\*const)\s+)?[\w:]+\s*')
INDEX = re.compile(rb'\*(\w+)\.offset\(([0-9]+) as ::core::ffi::c_int as isize\)')


def candidates(source):
    result = []
    uses = Counter(IDENTIFIER.findall(source))
    for fn in FUNCTION.finditer(source):
        if uses[fn[1]] < 2 or b".offset(" not in fn[3]:
            continue
        params = [ARGUMENT.fullmatch(part) for part in fn[2].split(b",") if part.strip()]
        if not all(params):
            continue
        pointers = {p[1] for p in params if p[2]}
        if not pointers:
            continue
        indices = [(name, int(index)) for name, index in INDEX.findall(fn[3]) if name in pointers]
        counts = Counter(name for name, index in indices)
        mentions = Counter(IDENTIFIER.findall(fn[3]))
        if any(counts[name] == 0 or counts[name] != mentions[name] for name in pointers):
            continue
        declaration_sha = hashlib.sha256(fn[0]).hexdigest()
        bounds = {name.decode(): 1 + max(index for arg, index in indices if arg == name) for name in pointers}
        result.append((declaration_sha, fn[1].decode(), len(indices), bounds))
    return result


def rank(link_path):
    data = link_path.read_bytes()
    by_source = {}
    groups = {}

    def inspect(archive, sha, source):
        if sha not in by_source:
            by_source[sha] = candidates(source)
        for definition, name, count, bounds in by_source[sha]:
            row = groups.setdefault(definition, {
                "name": name,
                "definition_sha256": definition,
                "offset_accesses_per_copy": count,
                "required_array_elements": bounds,
                "copies": 0,
                "archives": set(),
            })
            row["copies"] += 1
            row["archives"].add(str(archive))

    inventory = measure(json.loads(data), inspect)
    if link_path.read_bytes() != data:
        raise ValueError("release changed during the scan")
    for row in groups.values():
        row["archives"] = sorted(row["archives"])
        row["offset_accesses_across_copies"] = row["copies"] * row["offset_accesses_per_copy"]
    return {"link_report_sha256": hashlib.sha256(data).hexdigest(), "binary_sha256": inventory["binary_sha256"],
            "helpers": sorted(groups.values(), key=lambda row: (-row["offset_accesses_across_copies"], row["definition_sha256"]))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link_report", type=Path)
    args = parser.parse_args()
    print(json.dumps(rank(args.link_report), indent=2, sort_keys=True))
