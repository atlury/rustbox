#!/usr/bin/env python3
"""Count unused C types on one compiler selection, then substitute the verified archives in one multicall link."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from audit_linked_pointers import measure
from build_unused_c_types import replay_layer
from check_cargo_private_inlines import ROOT, digest
from link_rustbox_multicall import namespace_acl_library, namespace_grep_library
from preview_cargo_multicall import preview_link, qualified_inputs
from preview_curl_month_array import namespace as curl_inputs
from preview_diffutils_help_catalogs import namespace as diffutils_inputs
from preview_gawk_ctype import namespace as gawk_inputs
from prune_private_inlines import POINTER
from qualify_iproute2_combined_names import write_result
from verify_c_string_sources import syntax_tool


def simple_namespace(package, mapper):
    def namespace(path, residues, release, stage):
        archive, symbols = mapper(path, stage)
        if residues or symbols != release[package + "_namespaced_symbols"]:
            raise ValueError(f"{package} C linkage differs from the control")
        return archive, []
    return namespace


PACKAGES = {
    "acl-2.4.0": simple_namespace("acl", namespace_acl_library),
    "curl-8.23.0": curl_inputs,
    "diffutils-3.12": diffutils_inputs,
    "gawk-5.4.0": gawk_inputs,
    "grep-3.12": simple_namespace("grep", namespace_grep_library),
}


def plan(link, pilots, *, identical_foreign=False):
    raw = link.read_bytes()
    release = json.loads(raw)
    rows, sources = {}, {}
    for directory in pilots:
        row = json.loads((directory / "pilot.json").read_bytes())
        key = row["archive"]
        if (key in rows or (not identical_foreign and Path(key).parts[2] not in PACKAGES)
                or release["source_library_sha256"].get(key) != row["control_sha256"]
                or digest(directory / Path(key).name) != row["candidate_sha256"]
                or (row["candidate_sha256"] == row["control_sha256"]) != identical_foreign
                or row["raw_pointer_types_removed"] <= 0):
            raise ValueError(f"unexpected cold archive for {key}")
        rows[key] = dict(directory=directory.resolve().relative_to(ROOT).as_posix(), pilot=row)
        sources[key] = {}

    if not rows:
        raise ValueError("no archives selected")
    frequency = Counter()
    pointers = {}
    with TemporaryDirectory() as tmp:
        store = Path(tmp)
        def observe(archive, module, checksum, data):
            key = str(archive)
            sha = checksum.hex()
            frequency[sha] += 1
            if sha not in pointers:
                pointers[sha] = len(POINTER.findall(data))
            if key in rows:
                if str(module) in sources[key]:
                    raise ValueError(f"duplicate compiler input in {key}")
                sources[key][str(module)] = sha
                blob = store / sha
                if not blob.exists():
                    blob.write_bytes(data)

        audit = measure(release, inspect_module=observe, include_standalone_modules=True)
        def totals():
            return dict(all=sum(n * pointers[k] for k, n in frequency.items()),
                        counting_identical_files_once=sum(pointers[k] for k, n in frequency.items() if n))
        before = totals()
        if any(before[k] != audit[k]["raw_pointer_type_tokens"] for k in before):
            raise ValueError("source enumeration differs from the control census")
        if identical_foreign:
            from build_current_foreign_declarations import replay_compiler_layer
            apply = replay_compiler_layer
        else:
            scanner = syntax_tool("unused-c-types")
            def apply(modules, read, row):
                return replay_layer(modules, read, row, scanner)
        for key, modules in sources.items():
            def read(module):
                return (store / modules[module]).read_bytes()
            row = rows[key]["pilot"]
            changes = apply(modules, read, row)
            removed = 0
            for module, data in changes.items():
                old, new = modules[module], sha256(data).hexdigest()
                pointers[new] = len(POINTER.findall(data))
                removed += pointers[old] - pointers[new]
                frequency[old] -= 1
                frequency[new] += 1
            if removed != row["raw_pointer_types_removed"]:
                raise ValueError(f"source recount differs from compiler receipt for {key}")
        after = totals()
    if link.read_bytes() != raw:
        raise ValueError("link changed during source replay")
    return dict(parent_link_sha256=sha256(raw).hexdigest(), parent_binary_sha256=audit["binary_sha256"],
                counts={k: dict(before=before[k], after=after[k]) for k in before}, archives=rows)


def relink(link, log, selection, output):
    raw = link.read_bytes()
    selected = selection.read_bytes()
    report = json.loads(selected)
    release = json.loads(raw)
    if report["parent_link_sha256"] != sha256(raw).hexdigest() or report["parent_binary_sha256"] != release["binary"]["sha256"]:
        raise ValueError("compiler selection belongs to a different control")
    stages = {}
    for key, item in report["archives"].items():
        directory = ROOT / item["directory"]
        row = item["pilot"]
        if row["archive"] != key or row != json.loads((directory / "pilot.json").read_bytes()):
            raise ValueError(f"cold compiler receipt changed for {key}")
        stages[key] = qualified_inputs(release, directory, row, PACKAGES[Path(key).parts[2]])

    def prepare(name, stage):
        objects, changed, hashes = [], set(), {}
        for key, build in stages.items():
            files, replaced, meta = build(name, stage)
            objects.extend(files)
            changed.update(replaced)
            hashes[key] = meta["archive_sha256"]
        return objects, changed, dict(archive_sha256=hashes)

    preview_link(link, raw, log, output, prepare, lambda elf, stage: dict(selection_sha256=sha256(selected).hexdigest()))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    operations = p.add_subparsers(dest="operation", required=True)
    for operation in ("plan", "identical-foreign"):
        scan = operations.add_parser(operation)
        scan.add_argument("link", type=Path)
        scan.add_argument("output", type=Path)
        scan.add_argument("pilots", type=Path, nargs="+")
    build = operations.add_parser("link")
    for name in ("link", "log", "selection", "output"):
        build.add_argument(name, type=Path)
    args = p.parse_args()
    if args.operation != "link":
        write_result(args.output, plan(args.link, args.pilots, identical_foreign=args.operation == "identical-foreign"))
    else:
        relink(args.link, args.log, args.selection, args.output)
