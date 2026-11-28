#!/usr/bin/env python3
"""Replay byte-identical source selections against another linked source release."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from audit_linked_pointers import check_identical_layer, measure
from cargo_source_parent import cargo_origin
from prepare_identical_archives import prepare, row_origin, selected_receipts, validate_link

LAYER = "shared_va_list_layouts"


def rebase(link, manifests, output, *, layer=LAYER, allow_empty=False):
    if layer not in (LAYER, "closed_inline_groups", "shared_scalar_ffi"):
        raise ValueError("unknown byte-identical release layer")
    inputs = {p: p.read_bytes() for p in (link, *manifests)}
    if output.resolve() in {p.resolve() for p in inputs}:
        raise ValueError("write the rebased manifest to a separate file")
    parent = json.loads(inputs[link])
    if parent.get(layer):
        raise ValueError("expected a release before the requested source selection")
    choices = {}
    for path in manifests:
        for key, item in json.loads(inputs[path]).items():
            if choices.setdefault(key, item) != item:
                raise ValueError(f"conflicting source selections for {key}")
    selected, deferred = {}, {}
    for key, item in choices.items():
        row = item["pilot"]
        if row["archive"] != key or row["control_sha256"] != row["candidate_sha256"]:
            raise ValueError(f"expected a byte-identical archive for {key}")
        if parent["source_library_sha256"].get(key) != row["control_sha256"]:
            deferred[key] = "linked archive path or bytes changed"
        elif str(cargo_origin(parent, key)) != row_origin(row) or selected_receipts(parent, key, layer) != item["parent_receipts"]:
            deferred[key] = "parent compiler selection changed"
        elif layer == LAYER and key in parent.get("shared_ncurses_termtypes", {}):
            deferred[key] = "terminal layout needs a cold build on the new variadic inputs"
        else:
            selected[key] = item
    before = measure(parent)
    if allow_empty and not selected and deferred:
        records, changes = {}, {}
        after = before
    else:
        prepare(selected, layer)
        records = validate_link(selected, parent["source_library_sha256"], parent, layer)
        candidate = {**parent, layer:records}
        after = measure(candidate)
        check_identical_layer(parent, candidate, before, after, layer)
        if layer in ("closed_inline_groups", "shared_scalar_ffi"):
            metric = "closed_inline_deltas" if layer == "closed_inline_groups" else "scalar_ffi_deltas"
            changes = {key: counts["raw_pointer_type_tokens"] for key, counts in after[metric].items()}
        else:
            changes = after["shared_va_list_layout_deltas"]
    if changes != {k:r["raw_pointer_types_removed"] for k,r in records.items()}:
        raise ValueError("source deltas differ from the cold-build receipts")
    data = (json.dumps(selected, indent=2, sort_keys=True) + "\n").encode()
    with TemporaryDirectory(dir=output.parent) as tmp:
        staged = Path(tmp) / "selection.json"
        staged.write_bytes(data)
        if any(p.read_bytes() != original for p, original in inputs.items()):
            raise ValueError("a source manifest or the release changed during replay")
        staged.replace(output)
    return dict(parent_link_sha256=sha256(inputs[link]).hexdigest(), binary_sha256=parent["binary"]["sha256"],
                manifest_sha256=sha256(data).hexdigest(), selected=len(selected), deferred=deferred,
                counts={group:{"before":before[group]["raw_pointer_type_tokens"],"after":after[group]["raw_pointer_type_tokens"]}
                        for group in ("all","counting_identical_files_once")})


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("link", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("manifests", nargs="+", type=Path)
    choice = p.add_mutually_exclusive_group()
    choice.add_argument("--closed-inlines", action="store_const", dest="layer", const="closed_inline_groups")
    choice.add_argument("--shared-scalar-ffi", action="store_const", dest="layer", const="shared_scalar_ffi")
    p.set_defaults(layer=LAYER)
    args = p.parse_args()
    print(json.dumps(rebase(args.link, args.manifests, args.output, layer=args.layer), indent=2, sort_keys=True))
