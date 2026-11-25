#!/usr/bin/env python3
"""Replay the tar source and reject altered archive, source and compiler receipts."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_linked_pointers import check_archive_counts, measure
from cargo_source_parent import cargo_origin
from check_cargo_private_inlines import digest
from tar_timespec_archive import selection


def test(parent):
    base = json.loads(parent.read_bytes())
    preview = json.loads((ROOT / "evidence/tar-borrowed-timespec-multicall.json").read_bytes())
    record = selection.pinned()
    row = record["pilot"]
    key, candidate = selection.key, selection.candidate_path(row)
    assert digest(ROOT / candidate) == row["candidate_sha256"] == preview["candidate"]["archive_sha256"]
    assert preview["candidate"]["sha256"] == record["preview_elf_sha256"]
    assert base["binary"]["sha256"] == preview["parent"]["sha256"]
    selected = deepcopy(base)
    selected[selection.field] = record
    hashes = selected["source_library_sha256"]
    assert hashes.pop(key) == row["control_sha256"]
    hashes[str(candidate)] = row["candidate_sha256"]
    assert cargo_origin(selected, str(candidate)) == Path(key) and selection.parent_view(selected) == base
    before = measure(base, archive_pair=(Path(key), Path(key)))
    after = measure(selected, archive_pair=(Path(key), candidate))
    check_archive_counts(base, selection.parent_view(selected), before, after, {key: row}, "tar_timestamp_deltas")
    assert after["tar_timestamp_deltas"][key]["raw_pointer_type_tokens"] == 7
    for mutate in ("archive", "bytes", "source", "parent"):
        broken = deepcopy(selected)
        if mutate == "archive":
            broken["source_library_sha256"][key] = row["control_sha256"]
        elif mutate == "bytes":
            broken["source_library_sha256"][str(candidate)] = "0" * 64
        elif mutate == "source":
            broken[selection.field]["pilot"]["candidate_sources_sha256"] = "0" * 64
        else:
            broken["linked_foreign_declaration_proofs"].pop(key)
        try:
            selection.parent_view(broken)
        except ValueError:
            continue
        raise AssertionError("invalid tar archive selection accepted")
    print(f"Verified all {row['compiler_selected_sources']} tar compiler sources and seven removed pointer types.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packed_curl_parent", type=Path)
    args = parser.parse_args()
    test(args.packed_curl_parent)
