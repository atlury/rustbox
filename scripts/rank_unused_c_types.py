#!/usr/bin/env python3
"""Scan every selected staticlib crate once for unused generated C types."""
# SPDX-License-Identifier: 0BSD
import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from audit_linked_pointers import measure
from build_unused_c_types import SELECTOR, substitute
from check_cargo_private_inlines import digest
from check_e2fsprogs_dirhash_arrays import source_list_digest
from verify_c_string_sources import syntax_tool


def rank(link, jobs):
    if jobs < 1:
        raise ValueError("expected a positive worker count")
    raw = link.read_bytes()
    release = json.loads(raw)
    scanner = digest(SELECTOR)
    tool = syntax_tool("unused-c-types")
    tool_hash = digest(tool)
    with TemporaryDirectory() as tmp:
        crates = {}
        def capture(archive, module, checksum, data):
            key = str(archive)
            if key not in crates:
                folder = Path(tmp) / str(len(crates))
                folder.mkdir()
                crates[key] = folder, {}
            folder, sources = crates[key]
            if module.is_absolute() or ".." in module.parts or str(module) in sources:
                raise ValueError(f"unexpected compiler input {module} for {key}")
            dest = folder / module
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            sources[str(module)] = checksum.hex()

        measured = measure(release, inspect_module=capture)
        def inspect(key):
            folder, sources = crates[key]
            changes, facts = substitute(folder, sources, tool)
            updated = {**sources, **{name: sha256(data).hexdigest() for name, data in changes.items()}}
            return key, dict(control_sha256=release["source_library_sha256"][key],
                             compiler_selected_sources=len(sources), parent_sources_sha256=source_list_digest(sources),
                             candidate_sources_sha256=source_list_digest(updated), **facts)
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            archives = dict(pool.map(inspect, sorted(crates)))
    if digest(SELECTOR) != scanner or digest(tool) != tool_hash or link.read_bytes() != raw:
        raise ValueError("compiler link or type-selection tool changed during the ranking")
    return dict(link_sha256=sha256(raw).hexdigest(), binary_sha256=measured["binary_sha256"], scanner_sha256=scanner,
                parent_raw_pointer_types=measured["all"]["raw_pointer_type_tokens"], archives=archives,
                projected_pointer_types=sum(row["raw_pointer_types_removed"] for row in archives.values()))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("link", type=Path)
    p.add_argument("--jobs", type=int, default=2)
    a = p.parse_args()
    print(json.dumps(rank(a.link, a.jobs), sort_keys=True, indent=2))
