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
from iproute2_address_protocol_archive import control_view
from iproute2_route_name_archives import additional_lookup_records, lookup_records, routing_lookup_pair
from test_routing_protocol_multicall import expected_binary, validate_coverage


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
preview = json.loads((ROOT / "evidence/iproute2-routing-protocol-multicall.json").read_bytes())
assert expected_binary(preview) == preview["candidate"]["sha256"]
selected["binary"] = {"sha256": preview["candidate"]["sha256"]}
assert expected_binary(preview, selected) == selected["binary"]["sha256"]
assert control_view(selected)["source_library_sha256"] == control_view(parent)["source_library_sha256"]
copies = additional_lookup_records(selected)
assert len(copies) == 17
for origin, row in lookup_records(selected).items():
    actual, before, after = routing_lookup_pair(selected, origin)
    assert actual == row and before == ROOT / row["archive"] and after == ROOT / routing.candidate_path(row)
    if origin in copies:
        assert copies[origin] == dict(archive=origin, control_sha256=row["control_sha256"], candidate_sha256=row["candidate_sha256"])
rejects(lambda: expected_binary(preview, parent))
rejects(lambda: expected_binary(preview, dict(selected, binary=preview["parent"])))
invalid = deepcopy(preview)
invalid["candidate"]["engine_archive_sha256"].pop("ss")
rejects(lambda: expected_binary(invalid, selected))
invalid = deepcopy(preview)
invalid["canonical"]["gcc"]["cases_per_mode"] -= 1
rejects(lambda: validate_coverage(preview, invalid))
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
print("Verified 18 source origins, both compiler recipes, all lookup archive pairs, and nine invalid comparisons or selections.")
