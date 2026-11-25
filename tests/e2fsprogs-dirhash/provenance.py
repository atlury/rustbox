#!/usr/bin/env python3
"""Check the link projection back to the exact archive and earlier source receipts."""
# SPDX-License-Identifier: GPL-2.0-only
from copy import deepcopy
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from e2fsprogs_dirhash_archives import candidate_path, control_view

base = Path("work/analysis/e2fsprogs-1.47.4/program-translations/rustbox-e2fsprogs-shared/debugfs/libdebugfs_audit.a")
before, after = "a" * 64, "b" * 64
candidate = str(candidate_path(base, after))
record = {"production_sha256": before, "candidate_sha256": after,
          "raw_offset_accesses_replaced": 40, "inlines": {"sha256": "first"},
          "second_inlines": None, "declarations": {"sha256": "foreign"}}
link = {"source_library_sha256": {candidate: after, "unaffected.a": "unchanged"},
        "linked_private_inline_proofs": {str(base): record["inlines"]},
        "linked_foreign_declaration_proofs": {str(base): record["declarations"]},
        "e2fsprogs_dirhash_arrays": {str(base): record}}

control = control_view(link)
assert control["source_library_sha256"] == {str(base): before, "unaffected.a": "unchanged"}
assert candidate in link["source_library_sha256"] and str(base) not in link["source_library_sha256"]

for field, key, value in (("source_library_sha256", str(base), before),
                          ("source_library_sha256", candidate, before),
                          ("linked_foreign_declaration_proofs", str(base), None),
                          ("linked_second_inline_proofs", str(base), {"sha256": "unexpected"})):
    other = deepcopy(link)
    other.setdefault(field, {})[key] = value
    try:
        control_view(other)
    except ValueError:
        continue
    raise AssertionError(f"accepted invalid {field}")
print("Matched the source control and rejected ambiguous archives, changed hashes and stale parent receipts.")
