#!/usr/bin/env python3
"""Rank linked applet archives by pointer types in apparently unused private C declarations."""
# SPDX-License-Identifier: 0BSD
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from audit_linked_pointers import measure
from batch_cargo_private_inlines import IDENTIFIER
from prune_private_inlines import POINTER

BLOCK = re.compile(rb'^(?:unsafe )?extern "C" \{\r?\n(.*?)^\}', re.MULTILINE | re.DOTALL)
DECL = re.compile(rb"    (?:fn (\w+)\(|static (?:mut )?(\w+):)")
MODULE = re.compile(rb"^(?:pub(?:\([^)]*\))? )?mod \w+", re.MULTILINE)


def estimate(source):
    """Recognize generated Rust formatting. Only the compiler can authorize an edit."""
    if MODULE.search(source):
        return 0, 0
    possible = []
    for block in BLOCK.finditer(source):
        # An attributed extern block may impose linking or configuration requirements.
        previous = source.rfind(b"\n", 0, max(block.start() - 1, 0))
        if source[previous + 1:block.start()].strip().startswith(b"#["):
            continue
        name = None
        attributed = False
        for line in block[1].splitlines():
            if name is None:
                if line.lstrip().startswith(b"#["):
                    attributed = True
                    continue
                match = DECL.match(line)
                if match is None or attributed:
                    if line.strip():
                        attributed = False
                    continue
                name = match[1] or match[2]
                pointers = 0
            pointers += len(POINTER.findall(line))
            if line.rstrip().endswith(b";"):
                possible.append((name, pointers))
                name = None
    if not possible:
        return 0, 0
    counts = Counter(IDENTIFIER.findall(source))
    selected = [pointers for name, pointers in possible if counts[name] == 1]
    return len(selected), sum(selected)


def rank(link_path):
    raw = link_path.read_bytes()
    link = json.loads(raw)
    by_file = {}
    archives = defaultdict(Counter)

    def inspect(archive, digest, source):
        if digest not in by_file:
            by_file[digest] = estimate(source)
        declarations, pointers = by_file[digest]
        row = archives[str(archive)]
        row["candidate_declarations"] += declarations
        row["candidate_pointer_types"] += pointers

    inventory = measure(link, inspect)
    if link_path.read_bytes() != raw:
        raise ValueError("release changed during ranking")
    rows = sorted((dict(archive=name, **row) for name, row in archives.items()),
                  key=lambda row: (-row["candidate_pointer_types"], row["archive"]))
    return {"link_report_sha256": hashlib.sha256(raw).hexdigest(), "binary_sha256": inventory["binary_sha256"],
            "linked_pointer_types": inventory["all"]["raw_pointer_type_tokens"], "archives": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link_report", type=Path)
    args = parser.parse_args()
    print(json.dumps(rank(args.link_report), indent=2, sort_keys=True))
