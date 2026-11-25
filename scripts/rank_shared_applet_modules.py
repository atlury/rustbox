#!/usr/bin/env python3
"""Rank identical compiled Rust modules with public C functions across distinct engines of a package."""
# SPDX-License-Identifier: 0BSD
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re

from audit_linked_pointers import METRICS, measure

EXPORT = re.compile(rb'^pub (?:unsafe )?extern "C" fn ([A-Za-z_][A-Za-z_0-9]*)\(', re.M)
CHAR_POINTER = rb"\*mut\s+::core::ffi::c_char"
NAME_ARRAY = re.compile(rb"^static mut (\w+): \[" + CHAR_POINTER + rb"; (\d+)\] = \[\n", re.M)
NULL_SLOT = rb"::core::ptr::null::<::core::ffi::c_char>\(\)\s+as\s+" + CHAR_POINTER
NAME_SLOT = rb'b"(?:[^"\\\r\n]|\\.)*\\0"\s+as\s+\*const u8\s+as\s+\*const ::core::ffi::c_char\s+as\s+' + CHAR_POINTER
SLOT = re.compile(rb"\s*(?:(?P<empty>" + NULL_SLOT + rb")|" + NAME_SLOT + rb"),")


def generated_name_tables(data):
    """Recognize only fully enumerated translated static char-pointer arrays."""
    tables = []
    for declaration in NAME_ARRAY.finditer(data):
        position = declaration.end()
        capacity = int(declaration[2])
        filled = empty = 0
        while slot := SLOT.match(data, position):
            if slot["empty"] is None:
                filled += 1
            else:
                empty += 1
            position = slot.end()
        if filled + empty == capacity and data.startswith(b"\n];", position):
            tables.append({"name": declaration[1].decode(), "capacity": capacity,
                           "literal_names": filled, "null_slots": empty})
    return tables


def rank(link_path, limit=None):
    raw = link_path.read_bytes()
    copies = defaultdict(lambda: defaultdict(list))
    metrics = {}

    def inspect(archive, module, sha, data):
        if sha not in metrics:
            exports = EXPORT.findall(data)
            count = len(METRICS["raw_pointer_type_tokens"].findall(data))
            metrics[sha] = (count, len(exports), [s.decode() for s in exports[:3]],
                            generated_name_tables(data) if exports and count else [])
        count, exports, _, _ = metrics[sha]
        if count and exports:
            package = archive.relative_to("work/analysis").parts[0]
            copies[package, sha][str(archive)].append(str(module))

    inventory = measure(json.loads(raw), inspect_module=inspect)
    rows = []
    for (package, sha), archives in copies.items():
        if len(archives) < 2:
            continue
        count, exports, names, tables = metrics[sha]
        modules = {path for paths in archives.values() for path in paths}
        rows.append({"package": package, "module_sha256": sha.hex(), "paths": sorted(modules),
                     "archive_count": len(archives), "raw_pointer_types_per_copy": count,
                     "repeated_types_across_archives": (len(archives) - 1) * count,
                     "c_function_definitions": exports, "example_functions": names,
                     "archives": sorted(archives), **({"static_name_tables": tables} if tables else {})})
    rows.sort(key=lambda r: (-r["repeated_types_across_archives"], r["package"], r["module_sha256"]))
    if link_path.read_bytes() != raw:
        raise ValueError("release changed during shared-module ranking")
    return {"link_report_sha256": hashlib.sha256(raw).hexdigest(), "binary_sha256": inventory["binary_sha256"],
            "groups": len(rows), "repeated_types_across_archives": sum(r["repeated_types_across_archives"] for r in rows),
            "modules": rows[:limit]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link_report", type=Path)
    parser.add_argument("--limit", type=int, help="emit the leading modules while retaining the complete totals")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    print(json.dumps(rank(args.link_report, args.limit), indent=2, sort_keys=True))
