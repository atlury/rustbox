#!/usr/bin/env python3
"""Share identical, compiler-selected C leaf structs within a translated Cargo archive."""
# SPDX-License-Identifier: 0BSD
import argparse
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess

from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import digest
from prune_private_inlines import POINTER
from rank_leaf_c_layouts import leaf_declarations
from share_stdio_layout import provider_namespace

MARKER = ".rustbox-leaf-layouts"
SELECTION = ".rustbox-leaf-layout-selection.json"


def verify_layout_syntax(crate, copies, scanner):
    requested = defaultdict(list)
    for name, modules in copies.items():
        for module in modules:
            requested[module].append(name)
    output = subprocess.check_output([scanner, crate], input=json.dumps(requested).encode())
    rows = json.loads(output)
    if set(rows) != set(requested):
        raise ValueError("syntax scan omitted a source module")
    fingerprints = {}
    for module, names in requested.items():
        data = (crate / module).read_bytes()
        if set(rows[module]) != set(names):
            raise ValueError(f"syntax scan omitted a layout in {module}")
        for name, (start, end, fields) in rows[module].items():
            if data[start:end] + b"\n" != copies[name][module]:
                raise ValueError(f"selected byte range differs from the parsed struct {module}::{name}")
            if fingerprints.setdefault(name, fields) != fields:
                raise ValueError(f"parsed field types differ across copies of {name}")


def substitute(crate, sources, selection=None, *, scanner=None):
    if selection is None:
        selection = json.loads((crate / SELECTION).read_bytes())
    copies = defaultdict(dict)
    for module in sorted(sources):
        data = (crate / module).read_bytes()
        if sha256(data).hexdigest() != sources[module]:
            raise ValueError(f"unexpected compiler input {module}")
        for declaration, fingerprint, fields in leaf_declarations(data):
            name = declaration[1].decode()
            if name not in selection or fingerprint != selection[name]["fingerprint"]:
                continue
            if fields != selection[name]["pointer_fields"] or module in copies[name]:
                raise ValueError(f"ambiguous declaration of {name} in {module}")
            # An outer attribute can change layout, visibility or compilation.
            if data[:declaration.start()].rstrip().endswith(b"]"):
                raise ValueError(f"additional attribute preceding {name} in {module}")
            copies[name][module] = declaration[0]

    if scanner is not None:
        verify_layout_syntax(crate, copies, scanner)

    edits = defaultdict(list)
    owners = {}
    expected = 0
    for name, spec in sorted(selection.items()):
        group = copies[name]
        if len(group) != spec["copies"] or len(group) < 2 or len(set(group.values())) != 1:
            raise ValueError(f"linked declarations differ from the ranking for {name}")
        owner = min(group)
        declaration = group[owner]
        namespace = provider_namespace(crate / "lib.rs", Path(owner))
        parts = namespace.with_suffix("").parts
        if namespace.suffix != ".rs" or not all(re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", p) for p in parts):
            raise ValueError(f"unexpected provider module {namespace}")
        replacement = ("pub use crate::" + "::".join((*parts, name)) + ";").encode()
        replacement += b"\n" * declaration.count(b"\n")
        consumers = sorted(group.keys() - {owner})
        for module in consumers:
            edits[module].append((declaration, replacement))
        expected += spec["pointer_fields"] * len(consumers)
        owners[name] = dict(provider=owner, consumers=consumers, **spec)

    changed = {}
    observed = 0
    for module, replacements in edits.items():
        original = data = (crate / module).read_bytes()
        for old, new in replacements:
            if data.count(old) != 1:
                raise ValueError(f"expected one complete declaration in {module}")
            data = data.replace(old, new)
        changed[module] = data
        observed += len(POINTER.findall(original)) - len(POINTER.findall(data))
    if observed != expected or not observed:
        raise ValueError("source pointer delta differs from the ranked duplicate fields")
    return changed, dict(leaf_layouts=owners, raw_pointer_types_removed=observed)


def select_layouts(link, ranking, archive, names):
    rank = json.loads(ranking.read_bytes())
    if len(names) != len(set(names)) or rank["link_report_sha256"] != digest(link):
        raise ValueError("select distinct layouts from a ranking of this release")
    selection = {}
    for row in rank["layouts"]:
        name = row["name"]
        if name not in names or archive not in row["archives"]:
            continue
        if name in selection:
            raise ValueError(f"ambiguous layout fingerprint for {name}")
        selection[name] = dict(fingerprint=row["declaration_and_field_types_sha256"],
                               copies=row["archives"][archive], pointer_fields=row["pointer_fields"])
    if set(selection) != set(names):
        raise ValueError("some selected types have no repeated definition in the archive")

    return selection


def build(link, archive, selection, output):
    def configure(crate):
        with (crate / SELECTION).open("x") as stream:
            json.dump(selection, stream, sort_keys=True)

    stage_selected_archive(link, output, archive, MARKER, Path(__file__).name, configure)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mounted", type=Path)
    p.add_argument("--replay", action="store_true")
    p.add_argument("--link", type=Path)
    p.add_argument("--ranking", type=Path)
    p.add_argument("--archive")
    p.add_argument("--layouts", nargs="+")
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    if args.mounted:
        compile_mounted_sources(args.mounted, substitute, MARKER, allow_identical=True)
    elif all((args.link, args.ranking, args.archive, args.layouts, args.output)):
        selection = select_layouts(args.link, args.ranking, args.archive, args.layouts)
        if args.replay:
            from build_checked_errno import replay
            from verify_c_string_sources import syntax_tool
            scanner = syntax_tool("leaf-layouts")
            row = replay(args.link, args.archive, args.output,
                         transform=lambda crate, sources: substitute(crate, sources, selection, scanner=scanner))
            print(json.dumps(row, sort_keys=True))
        else:
            build(args.link, args.archive, selection, args.output)
    else:
        p.error("supply the release, ranking, archive, layouts and output directory")
