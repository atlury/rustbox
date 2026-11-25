#!/usr/bin/env python3
"""Check the link projection back to the exact archive and earlier source receipts."""
# SPDX-License-Identifier: GPL-2.0-only
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from e2fsprogs_dirhash_archives import candidate_path, control_view, prepare, prior_stage
from audit_linked_pointers import unicode_namespace

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

# A later stage keeps the complete earlier compiler record for every selected archive.
root = Path(__file__).resolve().parents[2]
arrays = json.loads((root / "batches/e2fsprogs-dirhash-arrays.json").read_bytes())
hangul = json.loads((root / "batches/e2fsprogs-hangul-arrays.json").read_bytes())
assert {key: prior_stage(row, "hangul") for key, row in hangul.items()} == arrays
minimal = {"linked_private_inline_proofs": {key: row["inlines"] for key, row in arrays.items()}}
with tempfile.TemporaryDirectory() as tmp:
    manifest = Path(tmp) / "invalid.json"
    for stage, records in (("hangul", hangul), ("trie", {
        key: dict(row, trie={"parent_archive_sha256": row["candidate_sha256"],
                             "parent_sources_sha256": row["compiler_sources_sha256"]}) for key, row in hangul.items()
    })):
        for field in ("parent_archive_sha256", "parent_sources_sha256", None):
            changed = deepcopy(records)
            row = changed[next(iter(changed))]
            if field is None:
                del row[stage]
            else:
                row[stage][field] = "0" * 64
            manifest.write_text(json.dumps(changed))
            try:
                prepare(minimal, manifest, root)
            except ValueError as e:
                assert stage in str(e)
            else:
                raise AssertionError(f"accepted mismatched stage {stage}, field {field}")
print("Both Unicode stages reject altered archive or source parents and partial selections before rebuilding.")


# The expected map retains existing symbols and binds every permitted addition to an archive pair.
baseline = {Path(key).parent.name: ["existing_c_symbol"] for key in hangul}
expected = unicode_namespace(baseline, hangul, "hangul")
assert all("existing_c_symbol" in symbols and len(symbols) == 2 for symbols in expected.values())
stale = deepcopy(hangul)
stale[next(iter(stale))]["candidate_sha256"] = "0" * 64
try:
    unicode_namespace(baseline, stale, "hangul")
except ValueError:
    pass
else:
    raise AssertionError("accepted a private-symbol record for a different archive")
print("The private-symbol map retained existing C symbols and rejected an unmeasured archive.")
