#!/usr/bin/env python3
"""Enroll and install byte-identical Cargo archives with verified compiler-source substitutions."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from cargo_source_parent import cargo_origin, direct_crate, pinned_parent, row_origin
from check_cargo_private_inlines import ROOT, digest, layout

PROOFS = ("linked_private_inline_proofs", "linked_second_inline_proofs", "linked_foreign_declaration_proofs")


def parent_fields(layer):
    if layer == "closed_inline_groups":
        return (*parent_fields("shared_ncurses_termtypes"), "shared_ncurses_termtypes")
    if layer == "shared_ncurses_termtypes":
        return (*PROOFS, "shared_stdio_layouts", "native_c_strings", "shared_va_list_layouts")
    if layer == "shared_va_list_layouts":
        return (*PROOFS, "shared_stdio_layouts", "native_c_strings")
    if layer == "native_c_strings":
        return (*PROOFS, "shared_stdio_layouts")
    if layer == "shared_stdio_layouts":
        return PROOFS
    raise ValueError(f"unknown archive substitution layer {layer}")


def selected_receipts(link, key, layer):
    receipts = {}
    origin = str(cargo_origin(link, key))
    for field in parent_fields(layer):
        location = key if field not in PROOFS else origin
        if location in link.get(field, {}):
            receipts[field] = link[field][location]
    return receipts


def marker(archive, row, layer):
    suffix = {"native_c_strings": ".c-strings-", "shared_stdio_layouts": ".stdio-", "shared_va_list_layouts": ".va-list-",
              "shared_ncurses_termtypes": ".termtypes-", "closed_inline_groups": ".closed-inlines-"}[layer]
    return archive.with_name(archive.stem + suffix + row["candidate_sources_sha256"] + ".json")


def check_row(key, row):
    archive = Path(key)
    origin = Path(row_origin(row))
    if "rustc_archive" in row:
        if direct_crate(origin) is None:
            raise ValueError("unknown directly compiled engine")
    else:
        layout(origin)
    if origin != archive:
        pinned_parent(key, row)
    for name in ("control_sha256", "candidate_sha256", "candidate_sources_sha256", "parent_sources_sha256", "control_binary_sha256"):
        value = row[name]
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError(f"invalid {name} for {key}")
    if row["archive"] != key or row["control_sha256"] != row["candidate_sha256"]:
        raise ValueError("only an identical cold build can supply this archive")
    return ROOT / archive


def validate_link(manifest, hashes, proofs, layer):
    records = {}
    for key, item in manifest.items():
        row = item["pilot"]
        archive = check_row(key, row)
        stamp = marker(archive, row, layer)
        if (hashes.get(key) != row["control_sha256"] or str(cargo_origin(proofs, key)) != row_origin(row)
                or selected_receipts(proofs, key, layer) != item["parent_receipts"]
                or json.loads(stamp.read_bytes()) != item or digest(archive) != row["candidate_sha256"]):
            raise ValueError(f"{layer} archive or compiler receipt changed for {key}")
        records[key] = row
    if not records:
        raise ValueError("empty archive substitution manifest")
    return records


def install(item, candidate, layer):
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
        receipt.replace(marker(archive, row, layer))


def prepare(manifest, layer, *, mounted_direct=False):
    for key, item in manifest.items():
        row = item["pilot"]
        archive = check_row(key, row)
        if digest(archive) != row["control_sha256"]:
            raise ValueError(f"{layer} parent archive differs for {key}")
        stamp = marker(archive, row, layer)
        if stamp.exists() and json.loads(stamp.read_bytes()) == item:
            continue
        with TemporaryDirectory(dir=archive.parent) as temp:
            root = Path(temp)
            link = pinned_parent(key, row)
            link["binary"] = {"sha256": row["control_binary_sha256"]}
            for field, receipt in item["parent_receipts"].items():
                location = key if field not in PROOFS else row_origin(row)
                target = link.setdefault(field, {})
                if target.get(location, receipt) != receipt:
                    raise ValueError("archived compiler receipt differs from the pinned parent")
                target[location] = receipt
            (root / "parent.json").write_text(json.dumps(link))
            if mounted_direct and layer == "closed_inline_groups":
                from build_staged_c_strings import compile_archive
                if "rustc_archive" not in row:
                    raise ValueError("expected a directly compiled closed helper archive")
                (root / "built").mkdir()
                compile_archive(root / "parent.json", root / "built", key, sorted(row["dead_sites"]), closed_inlines=True)
            elif layer == "closed_inline_groups":
                from build_closed_inlines import build
                build(root / "parent.json", key, root / "built", sorted(row["dead_sites"]))
            elif mounted_direct:
                from build_staged_c_strings import compile_archive
                if "rustc_archive" not in row or layer not in ("native_c_strings", "shared_va_list_layouts"):
                    raise ValueError("expected a directly compiled archive substitution")
                (root / "built").mkdir()
                compile_archive(root / "parent.json", root / "built", key,
                                sorted(row["modules"]) if layer == "native_c_strings" else row["reexporting_modules"],
                                va_list_layout=layer == "shared_va_list_layouts", static_arrays="static_array_selector_sha256" in row)
            elif layer == "shared_ncurses_termtypes":
                from build_ncurses_termtype_layouts import MARKER
                from cargo_archive_pilot import stage_selected_archive
                stage_selected_archive(root / "parent.json", root / "built", key, MARKER, "build_ncurses_termtype_layouts.py")
            elif layer == "shared_va_list_layouts":
                from build_va_list_layout_pilot import build
                build(root / "parent.json", key, root / "built", row["reexporting_modules"])
            elif layer == "native_c_strings":
                from build_c_string_literal_pilot import build
                build(root / "parent.json", root / "built", Path(key), sorted(row["modules"]),
                      static_arrays="static_array_selector_sha256" in row)
            else:
                from build_shared_stdio_pilot import build
                build(root / "parent.json", root / "built", Path(key), row["reexporting_modules"])
            if json.loads((root / "built/pilot.json").read_bytes()) != row:
                raise ValueError(f"cold compiler receipt differed for {key}")
            install(item, root / "built" / archive.name, layer)


def enroll(link_file, output, pilots, layer, *, previous_manifest=None):
    from audit_linked_pointers import measure, check_identical_layer
    original = link_file.read_bytes()
    link = json.loads(original)
    records, manifest = {}, {}
    previous_bytes = None
    if previous_manifest is not None:
        previous_bytes = previous_manifest.read_bytes()
        manifest = json.loads(previous_bytes)
        if validate_link(manifest, link["source_library_sha256"], link, layer) != link.get(layer):
            raise ValueError("previous manifest differs from the active linked source layer")
    for directory in pilots:
        row = json.loads((directory / "pilot.json").read_bytes())
        key = row["archive"]
        archive = check_row(key, row)
        if key in records or link["source_library_sha256"].get(key) != row["control_sha256"]:
            raise ValueError(f"duplicate archive or different parent: {key}")
        if key in manifest:
            if layer != "native_c_strings":
                raise ValueError(f"duplicate archive: {key}")
            from verify_c_string_sources import check_extension
            check_extension(manifest[key]["pilot"], row)
        manifest[key] = dict(pilot=row, parent_receipts=selected_receipts(link, key, layer))
        records[key] = row
        if digest(archive) != row["control_sha256"] or digest(directory / archive.name) != row["candidate_sha256"]:
            raise ValueError(f"missing compiler output for {key}")
    # Bind the cold builds to this actual link, including all compiler source
    # hashes. Cached receipts from an earlier release may have the same inputs.
    base = dict(link)
    base.pop(layer, None)
    current = {**base, layer: records}
    for key, row in records.items():
        origin = cargo_origin(link, key)
        if str(origin) != row_origin(row):
            raise ValueError(f"cold build used the wrong Cargo origin for {key}")
        pair = (origin, Path(key))
        previous = base
        if previous_manifest is not None and key in link[layer]:
            previous = {**base, layer: {key: link[layer][key]}}
        check_identical_layer(previous, {**base, layer: {key: row}}, measure(previous, archive_pair=pair),
                              measure(current, archive_pair=pair), layer)
    for directory in pilots:
        row = json.loads((directory / "pilot.json").read_bytes())
        key = row["archive"]
        install(manifest[key], directory / Path(key).name, layer)
    validate_link(manifest, link["source_library_sha256"], link, layer)
    if (link_file.read_bytes() != original
            or (previous_manifest is not None and previous_manifest.read_bytes() != previous_bytes)):
        raise ValueError("link or previous manifest changed during enrollment")
    with TemporaryDirectory(dir=output.parent) as directory:
        staged = Path(directory) / "manifest.json"
        staged.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        staged.replace(output)


def main(layer):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("enroll")
    p.add_argument("link", type=Path)
    p.add_argument("manifest", type=Path)
    p.add_argument("pilots", nargs="+", type=Path)
    p.add_argument("--extend", type=Path, metavar="LINKED_MANIFEST", help="carry forward every existing verified entry")
    p = sub.add_parser("prepare")
    p.add_argument("manifest", type=Path)
    if layer in ("native_c_strings", "shared_va_list_layouts", "closed_inline_groups"):
        p.add_argument("--cargo-only", action="store_true",
                       help="the Linux linker prepares direct-rustc engines after building their parents")
    args = parser.parse_args()
    if args.command == "prepare":
        manifest = json.loads(args.manifest.read_bytes())
        if getattr(args, "cargo_only", False):
            manifest = {k: item for k, item in manifest.items() if "rustc_archive" not in item["pilot"]}
        prepare(manifest, layer)
    else:
        enroll(args.link, args.manifest, args.pilots, layer, previous_manifest=args.extend)
