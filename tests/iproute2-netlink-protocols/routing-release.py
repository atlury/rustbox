#!/usr/bin/env python3
"""Check all routing archive selections, both compiler recipes and rejection of stale sources."""
# SPDX-License-Identifier: GPL-2.0-or-later
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_linked_pointers import measure
from cargo_source_parent import cargo_origin, pinned_parent, row_origin
import stage_routing_protocol_archives as routing


def rejects(action):
    try:
        action()
    except ValueError:
        return
    raise AssertionError("accepted an invalid routing archive or source receipt")


parent = routing.parent_build_link()
selected = routing.select(parent)
rows = selected[routing.FIELD]
assert len(rows) == 18 and routing.parent_view(selected) == parent
for key, row in rows.items():
    target = routing.candidate_path(row)
    origin = cargo_origin(selected, str(target))
    assert str(origin) == row_origin(row)
    next_pilot = {"archive": str(target), "control_sha256": row["candidate_sha256"],
                  "rustc_archive" if "rustc_archive" in row else "cargo_archive": str(origin)}
    assert pinned_parent(str(target), next_pilot) == selected
    if Path(key).name in ("libbridge_audit.a", "libip_audit.a"):
        audit = measure(selected, archive_pair=(origin, target))
        assert audit["routing_protocol_deltas"][key]["raw_pointer_type_tokens"] == 267
key, *rest = rows
for field in ("candidate_sha256", "parent_sources_sha256", "module"):
    invalid = deepcopy(selected)
    invalid[routing.FIELD][key][field] = "incorrect"
    rejects(lambda: routing.parent_view(invalid))
invalid = deepcopy(selected)
del invalid["native_c_strings"][key]
rejects(lambda: routing.parent_view(invalid))
invalid = deepcopy(selected)
invalid["source_library_sha256"][key] = rows[key]["control_sha256"]
rejects(lambda: routing.parent_view(invalid))
print("Verified 18 source origins, both compiler recipes, and five invalid link selections.")
