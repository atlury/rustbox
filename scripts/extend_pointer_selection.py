#!/usr/bin/env python3
"""Extend an existing compiler selection using compatible, byte-identical archive receipts."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from collections import Counter
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from audit_linked_pointers import measure
from cargo_source_parent import cargo_origin, row_origin
from check_cargo_private_inlines import digest
from optimize_pointer_selections import best_chain
from prepare_identical_archives import prepare, selected_receipts, validate_link

LAYERS = {
    "shared_scalar_ffi": "scalar_ffi_deltas",
    "shared_variadic_ffi": "variadic_ffi_deltas",
    "shared_leaf_layouts": "leaf_layout_deltas",
}


def additions(parent, layer, manifest):
    selected, deferred = {}, {}
    later = list(LAYERS)[list(LAYERS).index(layer) + 1:]
    for key, item in manifest.items():
        row = item["pilot"]
        if (row["archive"] != key or row["candidate_sha256"] != row["control_sha256"]
                or row["raw_pointer_types_removed"] <= 0):
            raise ValueError(f"invalid byte-identical substitution for {key}")
        if key in parent.get(layer, {}):
            if parent[layer][key] != row:
                deferred[key] = "layer already selected with another receipt"
            elif item["parent_receipts"] != selected_receipts(parent, key, layer):
                deferred[key] = "preceding compiler inputs differ"
        elif row["control_sha256"] != parent["source_library_sha256"].get(key):
            deferred[key] = "linked control differs"
        elif str(cargo_origin(parent, key)) != row_origin(row) or item["parent_receipts"] != selected_receipts(parent, key, layer):
            deferred[key] = "preceding compiler inputs differ"
        elif any(key in parent.get(next_layer, {}) for next_layer in later):
            deferred[key] = "a later selection requires recompilation"
        else:
            selected[key] = item
    return selected, deferred


def improvements(original, proposals):
    """Choose an archive's best verified chain, retaining an incumbent on equal scores."""
    prefix = {k: v for k, v in original.items() if k not in LAYERS}
    remove, add, deferred = {}, {}, {}
    keys = sorted(set().union(*(manifest.keys() for manifest in proposals.values())))
    for key in keys:
        options, installed = {}, {}
        for layer in LAYERS:
            if key in original.get(layer, {}):
                row = original[layer][key]
                installed[layer] = dict(pilot=row, parent_receipts=selected_receipts(original, key, layer))
                options[layer] = [installed[layer]]
            if key in proposals.get(layer, {}):
                item = proposals[layer][key]
                row = item["pilot"]
                if (row["archive"] != key or row["candidate_sha256"] != row["control_sha256"]
                        or row["raw_pointer_types_removed"] <= 0):
                    raise ValueError(f"invalid byte-identical substitution for {key}")
                if item != installed.get(layer):
                    options.setdefault(layer, []).append(item)
        score, chosen = best_chain(prefix, key, options)
        if score <= sum(i["pilot"]["raw_pointer_types_removed"] for i in installed.values()):
            chosen = installed
        for layer in options:
            if installed.get(layer) != chosen.get(layer):
                if layer in installed:
                    remove.setdefault(layer, {})[key] = installed[layer]
                if layer in chosen:
                    add.setdefault(layer, {})[key] = chosen[layer]
            if key in proposals.get(layer, {}) and proposals[layer][key] != chosen.get(layer):
                deferred.setdefault(layer, {})[key] = "outside the highest-scoring compatible chain"
    return remove, add, deferred


def extend(link, manifests, output, *, replace_weaker=False):
    if output.exists():
        raise FileExistsError(output)
    inputs = {path: digest(path) for path in (link, *manifests.values())}
    original = json.loads(link.read_bytes())
    current = original.copy()
    enrolled, deferred = {}, {}
    proposals = {layer: json.loads(path.read_bytes()) for layer, path in manifests.items()}
    displaced = {}
    if replace_weaker:
        displaced, proposals, deferred = improvements(original, proposals)
        for layer, removed in displaced.items():
            current[layer] = {k: row for k, row in current[layer].items() if k not in removed}
            if not current[layer]:
                del current[layer]
    for layer in LAYERS:
        if layer not in proposals:
            continue
        selected, skipped = additions(current, layer, proposals[layer])
        if replace_weaker and skipped:
            raise ValueError("chosen archive chain failed its parent checks")
        if skipped:
            deferred[layer] = skipped
        if selected:
            prepare(selected, layer)
            records = validate_link(selected, current["source_library_sha256"], current, layer)
            current[layer] = {**current.get(layer, {}), **records}
            enrolled[layer] = selected
    if not enrolled:
        raise ValueError("no new compatible archive receipts")

    before, after = measure(original), measure(current)
    if before["binary_sha256"] != after["binary_sha256"] or before["packages"].keys() != after["packages"].keys():
        raise ValueError("linked executable or package set changed")
    expected = {pkg: Counter(counts) for pkg, counts in before["packages"].items()}
    total = 0
    for layer, items in displaced.items():
        for key, item in items.items():
            difference = before[LAYERS[layer]][key]
            if difference["raw_pointer_type_tokens"] != item["pilot"]["raw_pointer_types_removed"]:
                raise ValueError(f"displaced {layer} reduction differs for {key}")
            package = Path(key).relative_to("work/analysis").parts[0]
            expected[package].update(difference)
            total -= difference["raw_pointer_type_tokens"]
    for layer, items in enrolled.items():
        for key, item in items.items():
            difference = after[LAYERS[layer]][key]
            if difference["raw_pointer_type_tokens"] != item["pilot"]["raw_pointer_types_removed"]:
                raise ValueError(f"{layer} reduction disagrees with the cold archive for {key}")
            package = Path(key).relative_to("work/analysis").parts[0]
            expected[package].subtract(difference)
            total += difference["raw_pointer_type_tokens"]
    counts = {group: {"before": before[group]["raw_pointer_type_tokens"], "after": after[group]["raw_pointer_type_tokens"]}
              for group in ("all", "counting_identical_files_once")}
    if expected != after["packages"] or counts["all"]["before"] - counts["all"]["after"] != total:
        raise ValueError("compiler recount found unexplained changes")
    with TemporaryDirectory(dir=output.parent) as tmp:
        stage = Path(tmp) / "selection"
        stage.mkdir()
        release = stage / "release.json"
        release.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
        layers = {}
        for layer, entries in enrolled.items():
            manifest = stage / (layer + ".json")
            manifest.write_text(json.dumps(entries, indent=2, sort_keys=True) + "\n")
            layers[layer] = dict(archives=sorted(entries), manifest_sha256=digest(manifest))
        result = dict(parent_link_sha256=inputs[link], binary_sha256=after["binary_sha256"],
                      candidate_link_sha256=digest(release), layers=layers, deferred=deferred,
                      raw_pointer_types_removed=total, counts=counts)
        if displaced:
            result["displaced"] = {layer: {k: item["pilot"]["candidate_sources_sha256"] for k, item in items.items()}
                                   for layer, items in displaced.items()}
        (stage / "results.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        if any(digest(path) != checksum for path, checksum in inputs.items()):
            raise ValueError("input changed during the compiler recount")
        stage.rename(output)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--replace-weaker", action="store_true", help="choose higher-scoring compatible archive chains")
    for name in LAYERS:
        parser.add_argument("--" + name.replace("_", "-"), type=Path)
    args = parser.parse_args()
    manifests = {key: getattr(args, key) for key in LAYERS if getattr(args, key)}
    print(json.dumps(extend(args.link, manifests, args.output, replace_weaker=args.replace_weaker), indent=2, sort_keys=True))
