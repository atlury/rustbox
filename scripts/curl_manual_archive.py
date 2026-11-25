"""Bind the checked curl manual to its exact original archive and regenerate it from source receipts."""
# SPDX-License-Identifier: curl
import argparse
import json
from pathlib import Path
from qualified_cargo_archive import QualifiedArchive

from check_cargo_private_inlines import ROOT, digest
from check_e2fsprogs_dirhash_arrays import source_list_digest
from curl_manual import MODULE, replace_manual

KEY = "work/analysis/curl-8.23.0/translations/c2rust-0.22.1/curl-8.23.0-stable/target/release/libcurl_8_23_0_normalized_audit.a"
MANIFEST = ROOT / "batches/curl-manual.json"
selection = QualifiedArchive(KEY, "curl_manual", "packed-manual", MANIFEST, ROOT / "evidence/curl-manual-pilot.json")
candidate_path = selection.candidate_path
receipts = selection.receipts
pinned = selection.pinned
validate_parent = selection.validate_parent
parent_view = selection.parent_view


def pilot_parent_view(link):
    if "curl_manual" not in link:
        return link
    row = link["curl_manual"]["pilot"]
    return dict(parent_view(link), binary={**link["binary"], "sha256": row["control_binary_sha256"]})


def prepare(record, built=None):
    from build_curl_manual_pilot import build
    selection.prepare(record, build, built)


def pin(pilot, qualified, parent):
    from audit_linked_pointers import measure
    row = json.loads((pilot / "pilot.json").read_bytes())
    proof = json.loads(qualified.read_bytes())
    release = json.loads(parent.read_bytes())
    if proof["binary"]["sha256"] != row["control_binary_sha256"]:
        raise ValueError("pilot release differs")
    record = dict(pilot=row, parent_receipts=receipts(proof), selection_parent_sha256=release["binary"]["sha256"])
    for link in (proof, release):
        validate_parent(link, record)
    if digest(ROOT / KEY) != row["control_sha256"]:
        raise ValueError("curl control bytes have changed")
    sources = {}
    changes = {}

    def capture(archive, module, sha, data):
        if str(archive) != KEY or str(module) in sources:
            raise ValueError("unexpected curl compiler input")
        sources[str(module)] = sha.hex()
        if module == MODULE:
            _, delta = replace_manual(data)
            changes.update(delta)

    inputs = {k: {KEY: v} for k, v in record["parent_receipts"].items()}
    measure(dict(inputs, binary=release["binary"], source_library_sha256={KEY: row["control_sha256"]}), inspect_module=capture)
    if (len(sources) != row["compiler_selected_sources"] or source_list_digest(sources) != row["parent_sources_sha256"]
            or source_list_digest({**sources, str(MODULE): changes["candidate_module_sha256"]}) != row["candidate_sources_sha256"]
            or any(row[k] != v for k, v in changes.items())):
        raise ValueError("selected curl module or archive inputs differ")
    evidence = json.loads((ROOT / "evidence/curl-manual-pilot.json").read_bytes())
    if any(evidence[k] != v for k, v in row.items()):
        raise ValueError("curl comparison evidence differs from the proposed manifest")
    prepare(record, pilot / Path(KEY).name)
    MANIFEST.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--pin", nargs=3, type=Path, metavar=("PILOT", "QUALIFIED_LINK", "PARENT_LINK"))
    args = parser.parse_args()
    if args.prepare:
        prepare(pinned())
    else:
        pin(*args.pin)
