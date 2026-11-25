#!/usr/bin/env python3
"""The linked ip substitution retains the compiler inputs and receipts of its independently built parent."""
from copy import deepcopy
import hashlib
import json
from tempfile import TemporaryDirectory
from unittest.mock import patch
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from audit_linked_pointers import check_address_protocol_conversion
from iproute2_address_protocol_archive import (ARCHIVE, BRIDGE, BRIDGE_MODULE_SHA256, COPIES, MANIFEST, MODULE,
                                             candidate_path, control_view, pinned, pinned_copies, validate_copy_results, verify_sources)
from check_cargo_private_inlines import IPROUTE2_CARGO_ENGINES
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

# Missing copies or a divergent table would give a misleading batch-wide reduction.

with TemporaryDirectory() as scratch:
    root = Path(scratch)
    (root / MANIFEST).parent.mkdir()
    (root / MANIFEST).write_text(json.dumps(record))
    copies = {}
    for name in IPROUTE2_CARGO_ENGINES:
        if name == "ip":
            continue
        key = str(ARCHIVE.parents[2] / name / "release" / f"lib{name}_audit.a")
        copies[key] = dict(record, archive=key)
    copies[str(BRIDGE)] = dict(record, archive=str(BRIDGE), control_module_sha256=BRIDGE_MODULE_SHA256)
    (root / COPIES).write_text(json.dumps(copies))
    assert pinned_copies(root) == copies
    key = next(iter(copies))
    for invalid in ({k: v for k, v in copies.items() if k != key},
                    {**copies, key: dict(copies[key], candidate_module_sha256="different")},
                    {**copies, key: dict(copies[key], candidate_sha256="../other")}):
        (root / COPIES).write_text(json.dumps(invalid))
        try:
            pinned_copies(root)
        except ValueError:
            pass
        else:
            raise AssertionError("accepted invalid batch selection")
print("All 17 additional compiler-selected copies are required and each table must match the verified ip implementation.")

pilot = {"lookup_results_per_variant": 6320, "configurations": 4, "deferred_load_and_cache_checks_per_variant": 1, "memcheck_runs": 5}
result = {"archive_sha256": {archive: record["candidate_sha256"]}, "control_sha256": {archive: record["control_sha256"]},
          "image_id": "same-image", "test_input_sha256": {"oracle": "same-input"},
          "lookup_checks": dict(pilot, variants_compared_to_canonical=["ip-parent", "ip-candidate", "ip-candidate-memcheck"])}
with patch("iproute2_address_protocol_archive.comparison_inputs", return_value={"oracle": "same-input"}):
    validate_copy_results({archive: record}, result, pilot, "same-image")
    for changes in ({"archive_sha256": {}}, {"image_id": "another-image"}, {"test_input_sha256": {}},
                    {"lookup_checks": dict(result["lookup_checks"], memcheck_runs=4)}):
        try:
            validate_copy_results({archive: record}, {**result, **changes}, pilot, "same-image")
        except ValueError:
            pass
        else:
            raise AssertionError("accepted stale or partial canonical comparisons")
print("Archive comparisons reject changes to a tested archive, tool image, oracle or memory-check count.")


# A whole-executable total may also conceal a change attributed to the wrong package.
metric = "raw_pointer_type_tokens"
removed = record["raw_pointer_types_removed_in_pilot_module"]
package = ARCHIVE.relative_to("work/analysis").parts[0]
old = {"all": {metric: 400}, "packages": {package: {metric: 390}, "other": {metric: 10}}}
new = {"all": {metric: 400 - removed}, "packages": {package: {metric: 390 - removed}, "other": {metric: 10}},
       "iproute2_address_protocol_deltas": {archive: {metric: removed}}}
parent_link = dict(parent, binary={"dynamic_needed": ["libc"]})
candidate_link = dict(selected, binary={"dynamic_needed": ["libc"]})
check_address_protocol_conversion(parent_link, candidate_link, old, new)
for changed_link, changed_inventory in (
    (candidate_link, dict(new, all=old["all"])),
    (candidate_link, dict(new, packages=old["packages"])),
    (dict(candidate_link, binary={"dynamic_needed": []}), new),
    (dict(candidate_link, total_dispatch_names=0), new),
):
    try:
        check_address_protocol_conversion(parent_link, changed_link, old, changed_inventory)
    except ValueError:
        pass
    else:
        raise AssertionError("accepted an unexplained executable or inventory change")
print("The release comparison accounts for the complete inventory and preserves other packages and link inputs.")
