#!/usr/bin/env python3
"""Select the largest compatible chain of verified pointer reductions for each archive."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from cargo_source_parent import cargo_origin, row_origin
from check_cargo_private_inlines import digest
from compose_pointer_selections import compose
from prepare_identical_archives import selected_receipts
from rebase_va_list_layouts import ORDER


def best_chain(parent, key, options):
    checksum = parent["source_library_sha256"].get(key)
    if checksum is None:
        return 0, {}
    origin = str(cargo_origin(parent, key))
    states = [(0, {}, parent)]
    for layer in ORDER:
        if layer not in options:
            continue
        extended = []
        for score, chosen, current in states:
            receipts = selected_receipts(current, key, layer)
            for item in options[layer]:
                row = item["pilot"]
                if (row["control_sha256"] != checksum or row_origin(row) != origin
                        or item["parent_receipts"] != receipts
                        or (layer == ORDER[0] and key in parent.get("shared_ncurses_termtypes", {}))):
                    continue
                next_parent = {**current, layer: {**current.get(layer, {}), key: row}}
                extended.append((score + row["raw_pointer_types_removed"], {**chosen, layer: item}, next_parent))
        states.extend(extended)
    score, chosen, _ = max(states, key=lambda state: state[0])
    return score, chosen


def optimize(link, manifests, output):
    if output.exists():
        raise FileExistsError(output)
    inputs = {p: digest(p) for p in (link, *(path for files in manifests.values() for path in files))}
    parent = json.loads(link.read_bytes())
    requested = [layer for layer in ORDER if manifests.get(layer)]
    if requested and any(layer in parent for layer in ORDER[ORDER.index(requested[0]):]):
        raise ValueError("optimization needs a parent preceding the requested source layers")
    options = {}
    for layer, paths in manifests.items():
        if layer not in ORDER:
            raise ValueError(f"unknown source layer {layer}")
        for path in paths:
            for key, item in json.loads(path.read_bytes()).items():
                row = item["pilot"]
                if (key != row["archive"] or row["control_sha256"] != row["candidate_sha256"]
                        or row["raw_pointer_types_removed"] <= 0):
                    raise ValueError(f"expected a positive byte-identical receipt for {key}")
                choices = options.setdefault(key, {}).setdefault(layer, [])
                if item not in choices:
                    choices.append(item)
    picked = {layer: {} for layer in ORDER}
    expected = 0
    for key, choices in sorted(options.items()):
        score, chain = best_chain(parent, key, choices)
        for layer, item in chain.items():
            picked[layer][key] = item
        expected += score
    if not expected:
        raise ValueError("no matching compiler receipts on this parent")
    with TemporaryDirectory(dir=output.parent) as tmp:
        stage = Path(tmp) / "selection"
        stage.mkdir()
        layers = []
        for layer, entries in picked.items():
            if entries:
                manifest = stage / (layer + ".json")
                manifest.write_text(json.dumps(entries, indent=2, sort_keys=True) + "\n")
                layers.append((layer, [manifest]))
        recount = stage / "recount"
        measured = compose(link, recount, layers)
        if (any(row["deferred"] for row in measured["layers"].values()) or
                measured["counts"]["all"]["before"] - measured["counts"]["all"]["after"] != expected):
            raise ValueError("independent compiler recount disagrees with the selected chains")
        if any(digest(path) != checksum for path, checksum in inputs.items()):
            raise ValueError("release or candidate manifests changed during optimization")
        measured["sources"] = {str(output / Path(source).name) if Path(source).parent == stage else source: sha
                               for source, sha in measured["sources"].items()}
        (recount / "results.json").write_text(json.dumps(measured, indent=2, sort_keys=True) + "\n")
        proof = dict(link_sha256=inputs[link], binary_sha256=measured["binary_sha256"],
                     inputs={str(p): sha for p, sha in inputs.items() if p != link},
                     counts=measured["counts"], raw_pointer_types_removed=expected,
                     archives_considered=len(options), archives_selected=len(set().union(*picked.values())),
                     layers=measured["layers"])
        (stage / "results.json").write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
        stage.rename(output)
    return proof


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path)
    parser.add_argument("output", type=Path)
    for layer in ORDER:
        parser.add_argument("--" + layer.replace("_", "-"), type=Path, nargs="+", default=[])
    args = parser.parse_args()
    print(json.dumps(optimize(args.link, {k:getattr(args, k) for k in ORDER}, args.output), indent=2))
