#!/usr/bin/env python3
"""The packed curl manual can only replace its verified source archive."""
# SPDX-License-Identifier: curl
from copy import deepcopy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from curl_manual_archive import KEY, candidate_path, parent_view, pinned

record = pinned()
row = record["pilot"]
candidate = str(candidate_path(row))
parent = {"source_library_sha256": {KEY: row["control_sha256"]},
          **{key: {KEY: value} for key, value in record["parent_receipts"].items()}}
selected = dict(parent, curl_manual=record, source_library_sha256={candidate: row["candidate_sha256"]})
assert parent_view(selected) == parent
for case in ("digest", "ambiguous", "missing receipt", "different source"):
    broken = deepcopy(selected)
    if case == "digest":
        broken["source_library_sha256"][candidate] = "stale"
    elif case == "ambiguous":
        broken["source_library_sha256"].update(parent["source_library_sha256"])
    elif case == "missing receipt":
        del broken["linked_private_inline_proofs"][KEY]
    else:
        broken["curl_manual"]["pilot"]["control_module_sha256"] = "different"
    try:
        parent_view(broken)
    except ValueError:
        continue
    raise AssertionError(case)
print("Restored the curl parent and rejected stale, ambiguous and unverified selections.")
