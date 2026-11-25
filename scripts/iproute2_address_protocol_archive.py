"""Select and replay the compiler-verified IPRoute2 address-protocol archive."""
# SPDX-License-Identifier: GPL-2.0-or-later
import json
from pathlib import Path
import tempfile

from check_cargo_private_inlines import ROOT, digest
from check_e2fsprogs_dirhash_arrays import source_list_digest
from stage_iproute2_address_protocols import MODULE, compiler_inputs, replace_table

ARCHIVE = Path("work/analysis/iproute2-7.3.0/program-translations/cargo-target/ip/release/libip_audit.a")
MANIFEST = Path("batches/iproute2-address-protocols.json")
RECEIPTS = ("linked_private_inline_proofs", "linked_second_inline_proofs", "linked_foreign_declaration_proofs")


def candidate_path(record):
    return ARCHIVE.parent.parent / "address-protocols" / record["candidate_sha256"] / ARCHIVE.name


def pinned(repository=ROOT):
    record = json.loads((repository / MANIFEST).read_bytes())
    if record["archive"] != str(ARCHIVE) or set(record["parent_receipts"]) != set(RECEIPTS):
        raise ValueError("unexpected address-protocol archive manifest")
    return record


def validate_control(link, record):
    key = str(ARCHIVE)
    if (link["source_library_sha256"].get(key) != record["control_sha256"]
            or any(link[k].get(key) != record["parent_receipts"][k] for k in RECEIPTS)):
        raise ValueError("IPRoute2 address-protocol parent archive or source receipts differ")


def control_view(link):
    record = link.get("iproute2_address_protocols")
    if record is None:
        return link
    if record != pinned():
        raise ValueError("unexpected IPRoute2 address-protocol selection")
    hashes = link["source_library_sha256"].copy()
    if str(ARCHIVE) in hashes or hashes.pop(str(candidate_path(record)), None) != record["candidate_sha256"]:
        raise ValueError("address-protocol candidate is missing or ambiguous")
    hashes[str(ARCHIVE)] = record["control_sha256"]
    control = dict(link, source_library_sha256=hashes)
    del control["iproute2_address_protocols"]
    validate_control(control, record)
    return control


def verify_sources(record, sources, changes):
    if (len(sources) != record["compiler_selected_sources"] or any(record[k] != v for k, v in changes.items())
            or sources[str(MODULE)] != record["control_module_sha256"]
            or source_list_digest(sources) != record["parent_sources_sha256"]
            or source_list_digest({**sources, str(MODULE): changes["candidate_module_sha256"]}) != record["candidate_sources_sha256"]):
        raise ValueError("IPRoute2 compiler inputs differ from the pinned address-protocol substitution")


def prepare():
    from build_iproute2_address_protocol_pilot import build_pilot

    record = pinned()
    key = str(ARCHIVE)
    control = {"binary": {"sha256": record["control_binary_sha256"]},
               "source_library_sha256": {key: record["control_sha256"]},
               **{k: {key: v} for k, v in record["parent_receipts"].items()}}
    original, files = compiler_inputs(control, key)
    _, changes = replace_table(original)
    verify_sources(record, {str(k): v for k, v in files.items()}, changes)
    target = ROOT / candidate_path(record)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=target.parent) as scratch:
            output = Path(scratch) / "candidate"
            build_pilot(output, control)
            archive = output / ARCHIVE.name
            if digest(archive) != record["candidate_sha256"]:
                raise ValueError("fresh Cargo candidate differs from qualified archive")
            archive.replace(target)
    if digest(target) != record["candidate_sha256"]:
        raise ValueError("cached address-protocol archive differs from manifest")
    print(f"Verified address-protocol archive {record['candidate_sha256']}")
