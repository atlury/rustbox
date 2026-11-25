#!/usr/bin/env python3
"""Stage compiler-verified IPRoute2 routing archives under their digests for the multicall linker."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from build_routing_protocol_pilot import build
from check_cargo_private_inlines import ROOT, digest
from iproute2_route_name_archives import manifest, netlink_path, parent_build_link as netlink_parent

EVIDENCE = ROOT / "evidence/iproute2-routing-protocol-archives.json"
QUALIFICATION = {"profiles", "memcheck_runs", "canonical_source_sha256", "oracle_compilers", "lookup_driver_sha256"}


def candidate_path(row):
    parent = Path(row["archive"])
    value = row["candidate_sha256"]
    if (len(value) != 64 or any(c not in "0123456789abcdef" for c in value) or parent.is_absolute() or ".." in parent.parts
            or parent.parent.parent.name != "netlink-protocols" or parent.parent.name != row["control_sha256"]):
        raise ValueError("expected a pinned netlink archive and SHA-256")
    return parent.parents[2] / "routing-protocols" / value / parent.name


FIELD = "iproute2_routing_protocols"


def pinned():
    rows = json.loads(EVIDENCE.read_bytes())["verified"]
    return {key: {field: value for field, value in row.items() if field not in QUALIFICATION}
            for key, row in rows.items()}


def parent_build_link():
    """Reconstruct the tested IPRoute2 compiler inputs without a saved multicall ELF."""
    link = netlink_parent(netlink=True)
    netlink = manifest(netlink=True)
    native = json.loads((ROOT / "evidence/iproute2-native-c-string-archives.json").read_bytes())["verified"]
    rows = pinned()
    parent_sha, = {row["control_binary_sha256"] for row in rows.values()}
    hashes = {str(netlink_path(r)): r["candidate_sha256"] for r in netlink.values()}
    if hashes.keys() != rows.keys() or rows.keys() != native.keys():
        raise ValueError("incomplete pinned routing parents")
    for key, row in rows.items():
        if (hashes[key] != row["control_sha256"] or native[key]["candidate_sha256"] != hashes[key]
                or native[key]["candidate_sources_sha256"] != row["parent_sources_sha256"]):
            raise ValueError("routing parent differs from the byte-identical C-string archive")
    return dict(link, source_library_sha256=hashes, iproute2_netlink_protocols=netlink,
                native_c_strings=native, binary={"sha256": parent_sha})


def select(parent):
    """Bind every new link input to its verified archive and preceding source selection."""
    rows = pinned()
    hashes = parent["source_library_sha256"].copy()
    for key, row in rows.items():
        new = str(candidate_path(row))
        if hashes.pop(key, None) != row["control_sha256"] or new in hashes:
            raise ValueError(f"missing or conflicting routing archive: {key}")
        hashes[new] = row["candidate_sha256"]
    selected = dict(parent, source_library_sha256=hashes, **{FIELD: rows})
    if parent_view(selected) != parent:
        raise ValueError("cannot restore the exact routing parent")
    return selected


def parent_view(link):
    if FIELD not in link:
        return link
    rows = link[FIELD]
    if rows != pinned():
        raise ValueError("unexpected routing protocol records")
    hashes = link["source_library_sha256"].copy()
    for key, row in rows.items():
        candidate = str(candidate_path(row))
        native = link.get("native_c_strings", {}).get(key, {})
        if (key in hashes or hashes.pop(candidate, None) != row["candidate_sha256"]
                or native.get("candidate_sources_sha256") != row["parent_sources_sha256"]):
            raise ValueError(f"stale routing engine archive or preceding C-string sources: {key}")
        hashes[key] = row["control_sha256"]
    previous = dict(link, source_library_sha256=hashes)
    del previous[FIELD]
    return previous


def prepare(link, sources=None):
    from rank_routing_protocols import rank
    qualification = EVIDENCE.read_bytes()
    rows = json.loads(qualification)["verified"]
    ranking = rank(link)
    expected = {str(netlink_path(record)) for record in manifest(netlink=True).values()}
    if len(expected) != 18 or expected != rows.keys() or expected != ranking["engines"].keys():
        raise ValueError("expected the 18 qualified IPRoute2 engines and their netlink parents")
    installed = {}
    for key, row in sorted(rows.items()):
        inventory = ranking["engines"][key]
        if (key != row["archive"] or row["control_sha256"] != inventory["control_archive_sha256"]
                or digest(ROOT / key) != row["control_sha256"]
                or any(row[k] != v for k, v in inventory.items() if k != "control_archive_sha256")):
            raise ValueError(f"compiler sources or parent archive changed: {key}")
        dest = ROOT / candidate_path(row)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            with TemporaryDirectory(dir=dest.parent) as tmp:
                scratch = Path(tmp)
                if sources is None:
                    directory = scratch / "built"
                    build(link, directory, key)
                else:
                    directory = sources / Path(key).stem
                compiled = json.loads((directory / "pilot.json").read_bytes())
                wanted = {k: v for k, v in row.items() if k not in QUALIFICATION}
                # The parent executable may also contain newer, unrelated engines.
                # Match every compiler input and both complete archive digests.
                permitted = {ranking["binary_sha256"], wanted["control_binary_sha256"]}
                if compiled["control_binary_sha256"] not in permitted:
                    raise ValueError(f"unexpected compiler receipt for {key}")
                wanted["control_binary_sha256"] = compiled["control_binary_sha256"]
                if compiled != wanted:
                    raise ValueError(f"staged compiler receipt differs for {key}")
                artifact = scratch / dest.name
                shutil.copyfile(directory / dest.name, artifact)
                if digest(artifact) != row["candidate_sha256"]:
                    raise ValueError(f"changed routing archive: {artifact}")
                artifact.replace(dest)
        if digest(dest) != row["candidate_sha256"]:
            raise ValueError(f"invalid content-addressed routing archive: {dest}")
        installed[key] = str(dest.relative_to(ROOT))
    if digest(link) != ranking["link_report_sha256"] or EVIDENCE.read_bytes() != qualification:
        raise ValueError("selected multicall source or qualification changed during preparation")
    return dict(link_report_sha256=ranking["link_report_sha256"], qualification_sha256=sha256(qualification).hexdigest(),
                raw_pointer_types_removed=ranking["candidate_pointer_types"], archives=installed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path, nargs="?", help="default to the versioned compiler receipts")
    parser.add_argument("--native-manifest", type=Path, help="write the minimum preceding C-string selection")
    parser.add_argument("--built", type=Path, help="reuse the cold builds from the canonical lookup comparisons")
    args = parser.parse_args()
    if args.native_manifest:
        from prepare_identical_archives import selected_receipts
        parent = parent_build_link()
        records = {k: dict(pilot=r, parent_receipts=selected_receipts(parent, k, "native_c_strings"))
                   for k, r in parent["native_c_strings"].items()}
        with TemporaryDirectory(dir=args.native_manifest.parent) as temp:
            staged = Path(temp) / "manifest.json"
            staged.write_text(json.dumps(records, sort_keys=True, indent=2) + "\n")
            staged.replace(args.native_manifest)
    else:
        with TemporaryDirectory() as temp:
            link = args.link
            if link is None:
                link = Path(temp) / "parent.json"
                link.write_text(json.dumps(parent_build_link(), sort_keys=True))
            result = prepare(link.resolve(), args.built)
        print(json.dumps(result, sort_keys=True, indent=2))
