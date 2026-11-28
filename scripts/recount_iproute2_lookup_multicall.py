#!/usr/bin/env python3
"""Recount all selected Rust source bytes for an archive-qualified IPRoute2 multicall relink."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from audit_linked_pointers import METRICS, measure
from check_cargo_private_inlines import digest
from check_e2fsprogs_dirhash_arrays import source_list_digest
from link_rustbox_multicall import IPROUTE2_PROGRAMS


def recount(link, comparison, executable, qualification, transform):
    release_sha, link_test_sha, qualification_sha = map(digest, (link, comparison, qualification))
    release, tested, batch = (json.loads(p.read_bytes()) for p in (link, comparison, qualification))
    if (tested["parent_link_report_sha256"] != release_sha or tested["parent"]["sha256"] != release["binary"]["sha256"]
            or tested["candidate"]["sha256"] != digest(executable)
            or qualification_sha != tested.get("archive_evidence_sha256", tested.get("qualified_batch_sha256"))):
        raise ValueError("comparison does not bind the parent link, candidate ELF and qualified archives")
    # Single-engine receipts store one pilot directly. Whole-batch receipts
    # index their pilots by the archive path selected by the linker.
    entries = batch.get("verified")
    if entries is None and "engines" in batch:
        entries = {item["archive"]["archive"]: item for item in batch["engines"].values()}
        if len(entries) != len(batch["engines"]):
            raise ValueError("duplicate archive in the joint qualification")
    if entries is None:
        entries = {batch["archive"]["archive"]: batch}
    rows = {key: entry["archive"] if isinstance(entry["archive"], dict) else entry for key, entry in entries.items()}
    before = tested["parent"]["engine_archive_sha256"]
    after = tested["candidate"]["engine_archive_sha256"]
    if set(before) != set(IPROUTE2_PROGRAMS) or before.keys() != after.keys():
        raise ValueError("incomplete IPRoute2 final linker inputs")
    changed = set()
    inputs = {key: {} for key in rows}
    replacements = {}
    for key, row in rows.items():
        name = Path(key).name.removeprefix("lib").removesuffix("_audit.a")
        if (name in changed or row["archive"] != key or release["source_library_sha256"].get(key) != row["control_sha256"]
                or before[name] != row["control_sha256"] or after[name] != row["candidate_sha256"]):
            raise ValueError(f"compiler receipt does not match the linked archive: {key}")
        changed.add(name)
    if changed != {k for k in before if before[k] != after[k]}:
        raise ValueError("link changed different archives from the source selection")

    # Capture standalone engine source files as well as generated crate modules.
    counts = {}
    selected = Counter()
    seen = set()
    def visit(archive, module, checksum, data):
        key, name = str(archive), str(module)
        if archive not in seen:
            if archive.suffix not in (".a", ".o"):
                raise ValueError(f"unexpected compiler input owner {archive}")
            seen.add(archive)
            selected["archives" if archive.suffix == ".a" else "standalone_objects"] += 1
        selected["files"] += 1
        if key in rows:
            if name in inputs[key]:
                raise ValueError(f"duplicate module in {key}: {name}")
            inputs[key][name] = checksum.hex()
            row = rows[key]
            if name == row["module"]:
                data, facts = transform(data)
                if any(row[k] != value for k, value in facts.items()):
                    raise ValueError(f"selected lookup rewrite differs in {key}")
                checksum = sha256(data).digest()
                replacements[key] = {name: checksum.hex()}
        if checksum not in counts:
            counts[checksum] = {k: len(pattern.findall(data)) for k, pattern in METRICS.items()}
        selected.update(counts[checksum])
    control = measure(release, inspect_module=visit, include_standalone_modules=True)
    if any(selected[k] != control["all"][k] for k in ("archives", "standalone_objects", "files")):
        raise ValueError("source visitor did not enumerate the complete parent release")
    if rows.keys() != replacements.keys():
        raise ValueError("qualified module missing from compiler enumeration")
    for key, row in rows.items():
        modules = inputs[key]
        if (len(modules) != row["compiler_selected_sources"] or source_list_digest(modules) != row["parent_sources_sha256"]
                or source_list_digest({**modules, **replacements[key]}) != row["candidate_sources_sha256"]):
            raise ValueError(f"archive source-set digest differs for {key}")
    distinct = Counter()
    for metrics in counts.values():
        distinct.update(metrics)
    expected = sum(r["raw_pointer_types_removed"] for r in rows.values())
    if control["all"]["raw_pointer_type_tokens"] - selected["raw_pointer_type_tokens"] != expected:
        raise ValueError("whole compiler recount differs from the qualified archive changes")
    if (digest(link), digest(comparison), digest(qualification)) != (release_sha, link_test_sha, qualification_sha):
        raise ValueError("receipt changed during compiler enumeration")
    return dict(parent_link_sha256=release_sha, comparison_sha256=link_test_sha, qualified_archives_sha256=qualification_sha,
                parent_binary_sha256=tested["parent"]["sha256"], binary_sha256=tested["candidate"]["sha256"],
                archives=sorted(changed), all=selected, counting_identical_files_once=distinct,
                unique_files=len(counts), parent_all=control["all"], raw_pointer_types_removed=expected)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("table", choices=("dsfield", "group", "route-table", "group-route-tables"))
    for name in ("link", "comparison", "executable", "qualification"):
        p.add_argument(name, type=Path)
    a = p.parse_args()
    if a.table == "dsfield":
        from build_dsfield_names import transform
    elif a.table == "group":
        from build_group_names import transform
    elif a.table == "group-route-tables":
        from build_iproute2_group_route_tables import transform
    else:
        from build_iproute2_route_tables import transform
    print(json.dumps(recount(a.link, a.comparison, a.executable, a.qualification, transform), sort_keys=True, indent=2))
