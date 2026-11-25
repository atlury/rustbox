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
CHAR = rb"::core::ffi::c_char"
NAME_ARRAY = re.compile(
    rb"^(?P<public>pub )?static mut (?P<name>\w+): \[\*(?P<kind>mut|const)\s+" + CHAR +
    rb"; (?P<size>\d+)\] = \[\n", re.M)
NULL_VALUE = rb"::core::ptr::null::<" + CHAR + rb">\(\)"
NAME_VALUE = rb'b"(?:[^"\\\r\n]|\\.)*\\0"\s+as\s+\*const u8\s+as\s+\*const ' + CHAR


def slot_pattern(cast):
    return re.compile(rb"\s*(?:(?P<empty>" + NULL_VALUE + cast + rb")|" + NAME_VALUE + cast + rb"),")


SLOTS = {b"mut": slot_pattern(rb"\s+as\s+\*mut\s+" + CHAR), b"const": slot_pattern(b"")}


def name_table_spans(data):
    """Yield complete, literal-or-null arrays and their exact declaration spans."""
    for declaration in NAME_ARRAY.finditer(data):
        position = declaration.end()
        capacity = int(declaration["size"])
        slots = SLOTS[declaration["kind"]]
        filled = empty = 0
        while slot := slots.match(data, position):
            if slot["empty"] is None:
                filled += 1
            else:
                empty += 1
            position = slot.end()
        if filled + empty == capacity and data.startswith(b"\n];", position):
            yield declaration, position + 3, {"name": declaration["name"].decode(), "capacity": capacity,
                                            "literal_names": filled, "null_slots": empty}


def generated_name_tables(data):
    """Preserve the private mutable-table inventory in shared-module reports."""
    return [row for decl, _, row in name_table_spans(data)
            if not decl["public"] and decl["kind"] == b"mut"]


def rank_tables(link_path, limit=None):
    raw = link_path.read_bytes()
    by_module = {}
    groups = {}

    def inspect(archive, module, sha, data):
        if sha not in by_module:
            matches = []
            for decl, end, row in name_table_spans(data):
                source = data[decl.start():end]
                matches.append(dict(row, declaration_sha256=hashlib.sha256(source).hexdigest(),
                                    public=bool(decl["public"]), pointee=decl["kind"].decode(),
                                    raw_pointer_types_per_copy=len(METRICS["raw_pointer_type_tokens"].findall(source))))
            by_module[sha] = matches
        package = archive.relative_to("work/analysis").parts[0]
        for row in by_module[sha]:
            key = (package, row["declaration_sha256"])
            if key not in groups:
                groups[key] = dict(row, package=package, archives=defaultdict(list))
            groups[key]["archives"][str(archive)].append(str(module))

    inventory = measure(json.loads(raw), inspect_module=inspect)
    if link_path.read_bytes() != raw:
        raise ValueError("link report changed during static table scan")
    rows = []
    for row in groups.values():
        copies = sum(len(paths) for paths in row["archives"].values())
        row.update(copies=copies, raw_pointer_type_tokens=copies * row["raw_pointer_types_per_copy"])
        rows.append(row)
    rows.sort(key=lambda r: (-r["raw_pointer_type_tokens"], r["package"], r["name"], r["declaration_sha256"]))
    return {"binary_sha256": inventory["binary_sha256"], "link_report_sha256": hashlib.sha256(raw).hexdigest(),
            "groups": len(rows), "copies": sum(r["copies"] for r in rows),
            "raw_pointer_type_tokens": sum(r["raw_pointer_type_tokens"] for r in rows),
            "tables": rows[:limit]}


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
    parser.add_argument("--tables", action="store_true", help="rank complete literal/null name-table definitions across all selected modules")
    parser.add_argument("--limit", type=int, help="emit the leading modules while retaining the complete totals")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    scan = rank_tables if args.tables else rank
    print(json.dumps(scan(args.link_report, args.limit), indent=2, sort_keys=True))
