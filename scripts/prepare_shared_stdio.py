#!/usr/bin/env python3
"""Install byte-identical Cargo archives built from the enrolled shared stdio layouts."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from check_cargo_private_inlines import ROOT, digest, layout

PROOFS = ("linked_private_inline_proofs", "linked_second_inline_proofs", "linked_foreign_declaration_proofs")


def selected_receipts(link, key):
    return {f: link[f][key] for f in PROOFS if key in link.get(f, {})}


def marker(archive, row):
    return archive.with_name(archive.stem + ".stdio-" + row["candidate_sources_sha256"] + ".json")


def check_row(key, row):
    archive = Path(key)
    layout(archive)
    for name in ("control_sha256", "candidate_sha256", "candidate_sources_sha256", "parent_sources_sha256", "control_binary_sha256"):
        value = row[name]
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError(f"invalid {name} for {key}")
    if row["archive"] != key or row["control_sha256"] != row["candidate_sha256"]:
        raise ValueError("only an identical cold build can supply this archive")
    return ROOT / archive


def validate_link(manifest, hashes, proofs):
    records = {}
    for key, item in manifest.items():
        row = item["pilot"]
        archive = check_row(key, row)
        stamp = marker(archive, row)
        if (hashes.get(key) != row["control_sha256"] or selected_receipts(proofs, key) != item["parent_receipts"]
                or json.loads(stamp.read_bytes()) != item or digest(archive) != row["candidate_sha256"]):
            raise ValueError(f"FILE layout archive or compiler receipt changed for {key}")
        records[key] = row
    if not records:
        raise ValueError("empty FILE layout manifest")
    return records


def install(item, candidate):
    row = item["pilot"]
    archive = check_row(row["archive"], row)
    if digest(archive) != row["control_sha256"] or digest(candidate) != row["candidate_sha256"]:
        raise ValueError("cannot publish a changed static archive")
    with TemporaryDirectory(dir=archive.parent) as directory:
        staged = Path(directory) / archive.name
        shutil.copy2(candidate, staged)
        if digest(staged) != row["candidate_sha256"]:
            raise ValueError("archive copy mismatch")
        # The installed bytes are identical to the previous archive. Publish the
        # stamp last, so an interrupted installation can safely run again.
        staged.replace(archive)
        receipt = Path(directory) / "selection.json"
        receipt.write_text(json.dumps(item, indent=2, sort_keys=True) + "\n")
        receipt.replace(marker(archive, row))


def prepare(manifest):
    from build_shared_stdio_pilot import build
    for key, item in manifest.items():
        row = item["pilot"]
        archive = check_row(key, row)
        if digest(archive) != row["control_sha256"]:
            raise ValueError(f"FILE layout parent archive differs for {key}")
        stamp = marker(archive, row)
        if stamp.exists() and json.loads(stamp.read_bytes()) == item:
            continue
        with TemporaryDirectory(dir=archive.parent) as temp:
            root = Path(temp)
            link = {"binary": {"sha256": row["control_binary_sha256"]}, "source_library_sha256": {key: row["control_sha256"]},
                    **{field: {key: value} for field, value in item["parent_receipts"].items()}}
            (root / "parent.json").write_text(json.dumps(link))
            build(root / "parent.json", root / "built", Path(key), row["reexporting_modules"])
            if json.loads((root / "built/pilot.json").read_bytes()) != row:
                raise ValueError(f"cold compiler receipt differed for {key}")
            install(item, root / "built" / archive.name)


def enroll(link_file, output, pilots):
    from audit_linked_pointers import measure, check_shared_stdio
    link = json.loads(link_file.read_bytes())
    records, manifest = {}, {}
    for directory in pilots:
        row = json.loads((directory / "pilot.json").read_bytes())
        key = row["archive"]
        archive = check_row(key, row)
        if key in records or link["source_library_sha256"].get(key) != row["control_sha256"]:
            raise ValueError(f"duplicate archive or different parent: {key}")
        manifest[key] = dict(pilot=row, parent_receipts=selected_receipts(link, key))
        records[key] = row
        if digest(archive) != row["control_sha256"] or digest(directory / archive.name) != row["candidate_sha256"]:
            raise ValueError(f"missing compiler output for {key}")
    # Bind the cold builds to this actual link, including all compiler source
    # hashes. Cached receipts from an earlier release may have the same inputs.
    subset = {"binary": link["binary"], "source_library_sha256": {k: link["source_library_sha256"][k] for k in records}}
    for field in PROOFS:
        subset[field] = {key: link[field][key] for key in records if key in link.get(field, {})}
    current = dict(subset, shared_stdio_layouts=records)
    check_shared_stdio(subset, current, measure(subset), measure(current))
    for directory in pilots:
        row = json.loads((directory / "pilot.json").read_bytes())
        key = row["archive"]
        install(manifest[key], directory / Path(key).name)
    validate_link(manifest, subset["source_library_sha256"], subset)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("enroll")
    p.add_argument("link", type=Path)
    p.add_argument("manifest", type=Path)
    p.add_argument("pilots", nargs="+", type=Path)
    sub.add_parser("prepare").add_argument("manifest", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(json.loads(args.manifest.read_bytes()))
    else:
        enroll(args.link, args.manifest, args.pilots)
