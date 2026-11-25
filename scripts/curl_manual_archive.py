"""Bind the checked curl manual to its exact original archive and regenerate it from source receipts."""
# SPDX-License-Identifier: curl
import argparse
import json
from pathlib import Path
import re
import shutil
from tempfile import TemporaryDirectory

from check_cargo_private_inlines import ROOT, digest
from check_e2fsprogs_dirhash_arrays import source_list_digest
from curl_manual import MODULE, replace_manual

KEY = "work/analysis/curl-8.23.0/translations/c2rust-0.22.1/curl-8.23.0-stable/target/release/libcurl_8_23_0_normalized_audit.a"
RECEIPTS = ("linked_private_inline_proofs", "linked_second_inline_proofs", "linked_foreign_declaration_proofs")
MANIFEST = ROOT / "batches/curl-manual.json"


def candidate_path(row):
    if row["archive"] != KEY or not re.fullmatch(r"[a-f0-9]{64}", row["candidate_sha256"]):
        raise ValueError("unexpected curl manual archive")
    path = Path(KEY)
    return path.parents[1] / "packed-manual" / row["candidate_sha256"] / path.name


def receipts(link):
    return {name: link[name][KEY] for name in RECEIPTS if KEY in link.get(name, {})}


def pinned():
    record = json.loads(MANIFEST.read_bytes())
    pilot = json.loads((ROOT / "evidence/curl-manual-pilot.json").read_bytes())
    row = record["pilot"]
    candidate_path(row)
    if any(pilot[k] != v for k, v in row.items()):
        raise ValueError("curl manifest differs from the qualified pilot")
    return record


def validate_parent(link, record):
    if (link["source_library_sha256"].get(KEY) != record["pilot"]["control_sha256"]
            or receipts(link) != record["parent_receipts"]):
        raise ValueError("curl archive or compiler proof differs from the qualified parent")


def parent_view(link):
    if "curl_manual" not in link:
        return link
    record = link["curl_manual"]
    if record != pinned():
        raise ValueError("unrecognized curl manual substitution")
    row = record["pilot"]
    hashes = link["source_library_sha256"].copy()
    if KEY in hashes or hashes.pop(str(candidate_path(row)), None) != row["candidate_sha256"]:
        raise ValueError("ambiguous or stale packed curl manual")
    hashes[KEY] = row["control_sha256"]
    parent = dict(link, source_library_sha256=hashes)
    del parent["curl_manual"]
    validate_parent(parent, record)
    return parent


def pilot_parent_view(link):
    if "curl_manual" not in link:
        return link
    row = link["curl_manual"]["pilot"]
    return dict(parent_view(link), binary={**link["binary"], "sha256": row["control_binary_sha256"]})


def prepare(record, built=None):
    from build_curl_manual_pilot import build
    row = record["pilot"]
    destination = ROOT / candidate_path(row)
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=destination.parent) as tmp:
            scratch = Path(tmp)
            if built is None:
                link = {"binary": {"sha256": row["control_binary_sha256"]},
                        "source_library_sha256": {KEY: row["control_sha256"]},
                        **{name: {KEY: proof} for name, proof in record["parent_receipts"].items()}}
                source = scratch / "parent.json"
                source.write_text(json.dumps(link))
                build(source, scratch / "pilot")
                if json.loads((scratch / "pilot/pilot.json").read_bytes()) != row:
                    raise ValueError("cold curl build differs from the qualified pilot")
                built = scratch / "pilot" / destination.name
            if digest(built) != row["candidate_sha256"]:
                raise ValueError("unexpected packed curl archive bytes")
            staged = scratch / destination.name
            shutil.copyfile(built, staged)
            staged.replace(destination)
    if digest(destination) != row["candidate_sha256"]:
        raise ValueError("cached packed curl archive differs from manifest")


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
