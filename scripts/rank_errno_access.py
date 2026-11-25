#!/usr/bin/env python3
"""Rank value-only errno uses across the compiler inputs of a Rustbox link."""
# SPDX-License-Identifier: 0BSD
import argparse
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from audit_linked_pointers import measure
from build_checked_errno import SCANNER
from cargo_source_parent import cargo_origin
from check_cargo_private_inlines import digest
from verify_c_string_sources import syntax_tool


def rank(link, archives):
    raw = link.read_bytes()
    release = json.loads(raw)
    if len(set(archives)) != len(archives):
        raise ValueError("duplicate requested archive")
    by_hash = defaultdict(list)
    seen, roots, collisions = set(), set(), set()
    with TemporaryDirectory() as tmp:
        crate = Path(tmp)
        def collect(archive, module, checksum, data):
            key = str(archive)
            seen.add(key)
            if str(module) == "lib.rs":
                roots.add(key)
            if b"rustbox_errno" in data:
                collisions.add(key)
            if b"fn __errno_location(" not in data:
                return
            leaf = checksum.hex() + ".rs"
            if leaf not in by_hash:
                (crate / leaf).write_bytes(data)
            by_hash[leaf].append((key, str(module)))
        if archives:
            for key in archives:
                measure(release, inspect_module=collect, archive_pair=(cargo_origin(release, key), Path(key)))
        else:
            measure(release, inspect_module=collect)
        scanner = syntax_tool("errno-values")
        rows = json.loads(subprocess.check_output([scanner, crate], input=json.dumps(sorted(by_hash)).encode()))
    matches = defaultdict(dict)
    for name, (reads, writes, _) in rows.items():
        for key, module in by_hash[name]:
            if module == "lib.rs":
                collisions.add(key)
            if module in matches[key]:
                raise ValueError("repeated compiler input")
            matches[key][module] = (reads, writes)
    result = {}
    for key in sorted(roots - collisions):
        modules = matches[key]
        if modules:
            result[key] = dict(eligible_modules=len(modules), value_reads=sum(v[0] for v in modules.values()),
                               value_writes=sum(v[1] for v in modules.values()), net_pointer_declarations=len(modules)-1)
    if link.read_bytes() != raw:
        raise ValueError("link selection changed during source ranking")
    return dict(link_report_sha256=sha256(raw).hexdigest(), binary_sha256=release["binary"]["sha256"],
                scanner_sha256=digest(SCANNER), scanned_archives=len(seen), unique_declaration_sources=len(by_hash),
                scope=sorted(archives) if archives else "all linked compiler inputs", candidates=result,
                totals={k: sum(v[k] for v in result.values()) for k in
                        ("eligible_modules", "value_reads", "value_writes", "net_pointer_declarations")})


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("link", type=Path)
    p.add_argument("--archive", action="append", default=[])
    a = p.parse_args()
    print(json.dumps(rank(a.link, a.archive), indent=2, sort_keys=True))
