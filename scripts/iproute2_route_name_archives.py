"""Select and reproduce the scope/realm archives built on the address-protocol release."""
# SPDX-License-Identifier: GPL-2.0-or-later
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from build_iproute2_bridge_address_protocols import BRIDGE, compile_bridge
from check_cargo_private_inlines import ROOT, digest
from iproute2_address_protocol_archive import ARCHIVE, candidate_path as address_path, pinned, pinned_copies, selected_records


def candidate_path(record):
    path = address_path(record)
    return path.parents[2] / "route-names" / path.parent.name / path.name


def verified_records(link, records):
    parents = selected_records(link)
    if len(parents) != 18 or records.keys() != parents.keys():
        raise ValueError("scope/realm substitution requires all 18 linked parent archives")
    for key, row in records.items():
        parent = parents[key]
        if (row["archive"] != key or row["control_sha256"] != parent["candidate_sha256"]
                or row["control_module_sha256"] != parent["candidate_module_sha256"]
                or row["parent_sources_sha256"] != parent["candidate_sources_sha256"]
                or row["compiler_selected_sources"] != parent["compiler_selected_sources"]):
            raise ValueError(f"scope/realm compiler parent differs for {key}")
        candidate_path(row)
    return records


def manifest():
    return json.loads((ROOT / "batches/iproute2-route-names.json").read_bytes())


def parent_view(link):
    if "iproute2_route_names" not in link:
        return link
    rows = verified_records(link, link["iproute2_route_names"])
    if rows != manifest():
        raise ValueError("unexpected scope/realm manifest")
    parents = selected_records(link)
    hashes = link["source_library_sha256"].copy()
    for k, row in rows.items():
        prior = str(address_path(parents[k]))
        if prior in hashes or hashes.pop(str(candidate_path(row)), None) != row["candidate_sha256"]:
            raise ValueError(f"missing or ambiguous scope/realm archive for {k}")
        hashes[prior] = row["control_sha256"]
    control = dict(link, source_library_sha256=hashes)
    del control["iproute2_route_names"]
    return control


def parent_build_link():
    """Cold builds can reconstruct the pinned parent archives without a prior ELF on disk."""
    copies = pinned_copies()
    ip = pinned()
    parents = {ip["archive"]: ip, **copies}
    rows = manifest()
    hashes = {row["control_binary_sha256"] for row in rows.values()}
    if len(hashes) != 1:
        raise ValueError("expected a single verified parent executable")
    link = {"binary": {"sha256": hashes.pop()}, "iproute2_address_protocols": ip,
            "iproute2_address_protocol_copies": copies,
            "source_library_sha256": {str(address_path(row)): row["candidate_sha256"] for row in parents.values()}}
    for key, row in parents.items():
        for field, receipt in row["parent_receipts"].items():
            link.setdefault(field, {})[key] = receipt
    verified_records(link, rows)
    return link


def prepare(record, built=None, *, mounted_bridge=False):
    destination = ROOT / candidate_path(record)
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=destination.parent) as tmp:
            stage = Path(tmp)
            if built is None:
                from build_iproute2_route_names import check
                link = parent_build_link()
                if mounted_bridge:
                    actual = compile_bridge(link, stage, route_names=True)
                    archive = stage / BRIDGE.name
                else:
                    actual = check(link, record["archive"], stage / "build")
                    archive = stage / "build" / destination.name
                if actual != record:
                    raise ValueError("cold scope/realm build differs from manifest")
            else:
                archive = stage / destination.name
                shutil.copyfile(built, archive)
            if digest(archive) != record["candidate_sha256"]:
                raise ValueError("scope/realm archive differs from manifest")
            archive.replace(destination)
    if digest(destination) != record["candidate_sha256"]:
        raise ValueError("cached scope/realm archive differs from manifest")


def lookup_archive(link, key):
    """Archive currently providing a given address-protocol C interface."""
    parent_view(link)
    if "iproute2_route_names" in link:
        return candidate_path(link["iproute2_route_names"][key])
    return address_path(selected_records(link)[key])


def additional_lookup_records(link):
    records = link.get("iproute2_route_names", link.get("iproute2_address_protocol_copies", {}))
    return {k: row for k, row in records.items() if k != str(ARCHIVE)}


def build_control_view(link):
    if "iproute2_route_names" not in link:
        return link
    control = parent_view(link)
    hashes = {r["control_binary_sha256"] for r in link["iproute2_route_names"].values()}
    if len(hashes) != 1:
        raise ValueError("inconsistent parent executable hashes")
    return dict(control, binary={**control["binary"], "sha256": hashes.pop()})
