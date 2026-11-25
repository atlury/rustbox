#!/usr/bin/env python3
"""Stage the checked LZ4 dictionary after the selected stdio and native C-string sources."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import json
from tempfile import TemporaryDirectory
from pathlib import Path

from build_lz4_dictionary_pilot import MARKER
from cargo_archive_pilot import stage_selected_archive
from check_cargo_private_inlines import ROOT
from qualified_cargo_archive import QualifiedArchive

KEY = "work/analysis/lz4-1.11.1/translations/c2rust-0.22.1/lz4-1.11.1-stable/target/release/liblz4_1_11_1_normalized_audit.a"
selection = QualifiedArchive(
    KEY, "lz4_benchmark_dictionary", "packed-dictionary", ROOT / "batches/lz4-benchmark-dictionary.json",
    ROOT / "evidence/lz4-native-c-string-dictionary.json",
    extra_receipts=("shared_stdio_layouts", "native_c_strings", "shared_va_list_layouts", "shared_ncurses_termtypes"),
    evidence_section="dictionary",
)


def selected_link(parent):
    record = selection.pinned()
    selection.validate_parent(parent, record)
    row = record["pilot"]
    path = str(selection.candidate_path(row))
    hashes = parent["source_library_sha256"].copy()
    if path in hashes or selection.field in parent:
        raise ValueError("LZ4 dictionary already selected")
    del hashes[KEY]
    hashes[path] = row["candidate_sha256"]
    link = dict(parent, source_library_sha256=hashes, **{selection.field: record})
    if selection.parent_view(link) != parent:
        raise ValueError("cannot recover the exact LZ4 compiler parent")
    return link


def parent_manifests(directory, *, routing=False):
    from prepare_identical_archives import selected_receipts
    receipts = selection.pinned()["parent_receipts"]
    parent = {field: {KEY: value} for field, value in receipts.items()}
    manifests = {
        field: {KEY: dict(pilot=receipts[field], parent_receipts=selected_receipts(parent, KEY, field))}
        for field in ("native_c_strings", "shared_stdio_layouts")
    }
    if routing:
        from stage_routing_protocol_archives import parent_build_link
        previous = parent_build_link()
        for key, row in previous["native_c_strings"].items():
            manifests["native_c_strings"][key] = dict(pilot=row, parent_receipts=selected_receipts(previous, key, "native_c_strings"))
    directory.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=directory) as temp:
        for field, rows in manifests.items():
            staged = Path(temp) / (field + ".json")
            staged.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
            staged.replace(directory / staged.name)


def build(parent, output):
    stage_selected_archive(parent, output, KEY, MARKER, "build_lz4_dictionary_pilot.py")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--built", type=Path, help="reuse an already cold-built archive with the qualified digest")
    p.add_argument("--parent-manifests", type=Path, help="write the required byte-identical stdio and native string selections")
    p.add_argument("--routing", action="store_true", help="also include the 18 routing parents in the native string selection")
    args = p.parse_args()
    if args.parent_manifests and not args.built:
        parent_manifests(args.parent_manifests, routing=args.routing)
    elif not args.parent_manifests and not args.routing:
        selection.prepare(selection.pinned(), build, built=args.built)
    else:
        p.error("select either manifest generation or archive preparation")
