#!/usr/bin/env python3
"""Rank repeated repr(C) structs with pointer fields and C scalar, array, or self-referential field types."""
# SPDX-License-Identifier: 0BSD
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re

from audit_linked_pointers import measure
from prune_private_inlines import POINTER

STRUCT = re.compile(rb"^(?:#\[derive\(Copy, Clone\)\]\n#\[repr\(C\)\]|#\[repr\(C\)\]\n#\[derive\(Copy, Clone\)\])\n"
                    rb"pub struct (\w+) \{\n((?:    pub \w+: [^\n{}]+,\n)+)\}\n", re.M)
FIELD = re.compile(rb"    pub \w+: (.+),")
SCALAR = re.compile(rb"(?:[ui](?:8|16|32|64|128|size)|f(?:32|64)|::core::ffi::c_(?:void|s?char|uchar|u?short|"
                    rb"u?int|u?long(?:long)?|float|double))")
ALIAS = re.compile(rb"^pub type (\w+) = ([^;\n]+);$", re.M)


def leaf_layouts(data):
    aliases = dict(ALIAS.findall(data))
    layouts = []
    for struct in STRUCT.finditer(data):
        count = len(POINTER.findall(struct[0]))
        if not count:
            continue
        signature = []
        for line in struct[2].splitlines():
            field = FIELD.fullmatch(line)[1]
            # Arrays and pointers only add built-in constructors to the base type.
            constructors = []
            while True:
                if pointer := re.match(rb"^\*(?:const|mut) ", field):
                    constructors.append(pointer[0])
                    field = field[pointer.end():]
                elif array := re.fullmatch(rb"\[(.+); ([0-9]+)\]", field):
                    constructors.append(b"[" + array[2] + b"]")
                    field = array[1]
                else:
                    break
            # Resolve simple scalar aliases in this specific translation unit.
            visited = set()
            while field in aliases and field not in visited:
                visited.add(field)
                field = aliases[field]
            if not SCALAR.fullmatch(field) and not (field == struct[1] and constructors):
                break
            signature.append(b" ".join([*constructors, field]))
        else:
            fingerprint = sha256(struct[0] + b"\0" + b"\0".join(signature)).hexdigest()
            layouts.append((struct[1].decode(), fingerprint, count))
    return layouts


def rank(link, limit):
    raw = link.read_bytes()
    groups, cache = defaultdict(Counter), {}
    def inspect(archive, module, sha, data):
        if sha not in cache:
            cache[sha] = leaf_layouts(data)
        for key in cache[sha]:
            groups[key][str(archive)] += 1
    inventory = measure(json.loads(raw), inspect_module=inspect)
    if link.read_bytes() != raw:
        raise ValueError("link changed during layout scan")
    rows = []
    for (name, fingerprint, fields), counts in groups.items():
        archives = {k: v for k, v in sorted(counts.items()) if v > 1}
        repeats = sum(n - 1 for n in archives.values())
        if repeats:
            rows.append(dict(name=name, declaration_and_field_types_sha256=fingerprint, pointer_fields=fields,
                             repeated_definitions=repeats, pointer_types_in_repeats=fields * repeats, archives=archives))
    rows.sort(key=lambda row: (-row["pointer_types_in_repeats"], row["name"], row["declaration_and_field_types_sha256"]))
    return dict(binary_sha256=inventory["binary_sha256"], link_report_sha256=sha256(raw).hexdigest(), groups=len(rows),
                pointer_types_in_repeats=sum(row["pointer_types_in_repeats"] for row in rows), layouts=rows[:limit])


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("link", type=Path)
    p.add_argument("--limit", type=int)
    args = p.parse_args()
    print(json.dumps(rank(args.link, args.limit), sort_keys=True, indent=2))
