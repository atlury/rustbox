#!/usr/bin/env python3
"""Recount compatible byte-identical archive substitutions together on one saved multicall release."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from check_cargo_private_inlines import digest
from rebase_va_list_layouts import rebase


def _recount(link, output, layers):
    order = ("shared_va_list_layouts", "closed_inline_groups", "shared_scalar_ffi")
    requested = [name for name, _ in layers]
    if not requested or requested != [name for name in order if name in requested]:
        raise ValueError("expected distinct source layers in compiler order")
    original = json.loads(link.read_bytes())
    if any(name in original for name in order[order.index(requested[0]):]):
        raise ValueError("expected a parent preceding the requested source layers")
    sources = {p: digest(p) for p in (link, *(path for _, paths in layers for path in paths))}
    reports = {}
    parent = link
    for name, paths in layers:
        manifest = output / (name + ".json")
        result = rebase(parent, paths, manifest, layer=name, allow_empty=True)
        selected = json.loads(manifest.read_bytes())
        items = {key: item["pilot"] for key, item in selected.items()}
        measured = result["counts"]["all"]
        if (any(row["control_sha256"] != row["candidate_sha256"] for row in items.values())
                or measured["before"] - measured["after"] != sum(row["raw_pointer_types_removed"] for row in items.values())
                or result["binary_sha256"] != original["binary"]["sha256"]
                or result["manifest_sha256"] != digest(manifest)):
            raise ValueError(f"joint source count or executable changed during {name}")
        if reports:
            earlier = next(reversed(reports.values()))["counts"]
            if any(earlier[group]["after"] != counts["before"] for group, counts in result["counts"].items()):
                raise ValueError("consecutive compiler inventories disagree")
        previous = json.loads(parent.read_bytes())
        if items:
            previous[name] = items
        parent = output / (name + "-link.json")
        parent.write_text(json.dumps(previous, indent=2, sort_keys=True) + "\n")
        reports[name] = dict(result, candidate_link_sha256=digest(parent))
    first, last = reports[requested[0]], reports[requested[-1]]
    if any(digest(path) != checksum for path, checksum in sources.items()):
        raise ValueError("input manifests or release changed during composition")
    result = dict(binary_sha256=original["binary"]["sha256"], link_sha256=sources[link],
                  sources={str(path):checksum for path, checksum in sources.items()}, layers=reports,
                  counts={group:dict(before=first["counts"][group]["before"],after=last["counts"][group]["after"])
                          for group in first["counts"]})
    (output / "results.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return result


def compose(link, output, layers):
    if output.exists():
        raise FileExistsError(output)
    with TemporaryDirectory(dir=output.parent) as tmp:
        staged = Path(tmp) / "selection"
        staged.mkdir()
        result = _recount(link, staged, layers)
        staged.rename(output)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path)
    parser.add_argument("new_directory", type=Path)
    for name in ("shared-va-list-layouts", "closed-inline-groups", "shared-scalar-ffi"):
        parser.add_argument("--" + name, nargs="+", type=Path, metavar="MANIFEST")
    args = parser.parse_args()
    layers = [(name, paths) for name in ("shared_va_list_layouts", "closed_inline_groups", "shared_scalar_ffi")
              if (paths := getattr(args, name))]
    print(json.dumps(compose(args.link, args.new_directory, layers), sort_keys=True, indent=2))
