#!/usr/bin/env python3
"""The linked ip substitution retains the compiler inputs and receipts of its independently built parent."""
from copy import deepcopy
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from iproute2_address_protocol_archive import ARCHIVE, MODULE, candidate_path, control_view, pinned, verify_sources
from check_e2fsprogs_dirhash_arrays import source_list_digest

record = pinned()
archive = str(ARCHIVE)
candidate = str(candidate_path(record))
parent = {"source_library_sha256": {archive: record["control_sha256"]},
          **{key: {archive: receipt} for key, receipt in record["parent_receipts"].items()}}
selected = dict(parent, source_library_sha256={candidate: record["candidate_sha256"]}, iproute2_address_protocols=record)
assert control_view(selected) == parent
for change in ("ambiguous", "wrong-candidate", "lost-receipt", "altered-module"):
    broken = deepcopy(selected)
    if change == "ambiguous":
        broken["source_library_sha256"][archive] = record["control_sha256"]
    elif change == "wrong-candidate":
        broken["source_library_sha256"][candidate] = record["control_sha256"]
    elif change == "lost-receipt":
        broken["linked_private_inline_proofs"].clear()
    else:
        broken["iproute2_address_protocols"]["candidate_module_sha256"] = "unverified"
    try:
        control_view(broken)
    except ValueError:
        pass
    else:
        raise AssertionError(change)

source = {str(MODULE): record["control_module_sha256"], "lib.rs": hashlib.sha256(b"crate").hexdigest()}
changes = {k: record[k] for k in ("control_module_sha256", "candidate_module_sha256", "raw_pointer_types_removed_in_pilot_module")}
tiny = dict(record, compiler_selected_sources=len(source), parent_sources_sha256=source_list_digest(source),
            candidate_sources_sha256=source_list_digest({**source, str(MODULE): changes["candidate_module_sha256"]}))
verify_sources(tiny, source, changes)
for changed_sources in ({str(MODULE): source[str(MODULE)]}, {**source, "lib.rs": hashlib.sha256(b"other").hexdigest()}):
    try:
        verify_sources(tiny, changed_sources, changes)
    except ValueError:
        pass
    else:
        raise AssertionError("accepted a changed sibling compiler input")
print("Reconstructed the parent selection and rejected changed receipts, ambiguous archives and stale compiler inputs.")
