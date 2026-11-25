#!/usr/bin/env python3
"""The scope/realm layer can only replace the exact compiler-verified address-protocol archive set."""
# SPDX-License-Identifier: GPL-2.0-or-later
from copy import deepcopy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from iproute2_route_name_archives import build_control_view, candidate_path, manifest, parent_build_link, parent_view

parent = parent_build_link()
rows = manifest()
selected = dict(parent, source_library_sha256={str(candidate_path(row)): row["candidate_sha256"] for row in rows.values()},
                iproute2_route_names=rows, binary={"sha256": "new executable"})
assert build_control_view(selected) == parent
key = next(iter(rows))
for broken_case in ("missing", "stale digest", "wrong module", "two parents", "lost compiler input"):
    broken = deepcopy(selected)
    if broken_case == "missing":
        del broken["iproute2_route_names"][key]
    elif broken_case == "stale digest":
        broken["source_library_sha256"][str(candidate_path(rows[key]))] = "stale"
    elif broken_case == "wrong module":
        broken["iproute2_route_names"][key]["control_module_sha256"] = "different"
    elif broken_case == "two parents":
        broken["source_library_sha256"].update(parent["source_library_sha256"])
    else:
        broken["iproute2_route_names"][key]["compiler_selected_sources"] -= 1
    try:
        parent_view(broken)
    except ValueError:
        continue
    raise AssertionError(broken_case)
print("Reconstructed 18 scope/realm parents and rejected missing, stale and ambiguous inputs.")

# The newer layer must peel back to the scope/realm archives before the
# address-protocol parent can be reconstructed.
from iproute2_route_name_archives import netlink_control_view, netlink_path

parent = parent_build_link(netlink=True)
rows = manifest(netlink=True)
selected = dict(parent, source_library_sha256={str(netlink_path(r)): r["candidate_sha256"] for r in rows.values()},
                iproute2_netlink_protocols=rows, binary={"sha256": "new executable"})
assert netlink_control_view(selected) == parent
assert build_control_view(selected) == parent_build_link()
for field in ("control_sha256", "control_module_sha256", "parent_sources_sha256", "compiler_selected_sources"):
    broken = deepcopy(selected)
    broken["iproute2_netlink_protocols"][key][field] = None
    try:
        parent_view(broken)
    except ValueError:
        continue
    raise AssertionError(field)
ambiguous = deepcopy(selected)
ambiguous["source_library_sha256"].update(parent["source_library_sha256"])
try:
    parent_view(ambiguous)
except ValueError:
    pass
else:
    raise AssertionError("both parent and candidate selected")
print("Reconstructed all 18 netlink parents and rejected stale or ambiguous inputs.")
