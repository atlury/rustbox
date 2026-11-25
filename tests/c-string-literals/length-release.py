#!/usr/bin/env python3
"""Verify the Bison link's complete source change and reject an unrelated or stale selection."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_linked_pointers import check_archive_counts, measure
from bison_length_archive import selection
from cargo_source_parent import cargo_origin


def test(link):
    previous = json.loads(link.read_bytes())
    record = selection.pinned()
    row = record["pilot"]
    key, selected = selection.key, selection.candidate_path(row)
    after = deepcopy(previous)
    assert after["source_library_sha256"].pop(key) == row["control_sha256"]
    after["source_library_sha256"][str(selected)] = row["candidate_sha256"]
    after[selection.field] = record
    assert cargo_origin(after, str(selected)) == Path(key)
    assert selection.parent_view(after) == previous
    before = measure(previous, archive_pair=(Path(key), Path(key)))
    updated = measure(after, archive_pair=(Path(key), selected))
    check_archive_counts(previous, selection.parent_view(after), before, updated, {key: row}, "bison_length_deltas")
    assert updated["bison_length_deltas"][key]["raw_pointer_type_tokens"] == 450
    for field in ("archive hash", "compiler inputs", "parent proof"):
        stale = deepcopy(after)
        if field == "archive hash":
            stale["source_library_sha256"][str(selected)] = "0" * 64
        elif field == "compiler inputs":
            stale[selection.field]["pilot"]["candidate_sources_sha256"] = "0" * 64
        else:
            stale["linked_foreign_declaration_proofs"].pop(key)
        try:
            selection.parent_view(stale)
        except ValueError:
            continue
        raise AssertionError(f"accepted altered {field}")
    print(f"Verified {row['compiler_selected_sources']} Bison sources and {row['raw_pointer_types_removed']} removed pointer types.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("parent", type=Path)
    test(p.parse_args().parent)
