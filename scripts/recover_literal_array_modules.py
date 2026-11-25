#!/usr/bin/env python3
"""Retry differing C-string archives using modules whose edits occur only in static array initializers."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from audit_linked_pointers import measure
from build_c_string_literal_pilot import build, static_array_edits
from cargo_source_parent import cargo_origin
from check_cargo_private_inlines import ROOT, digest
from check_e2fsprogs_dirhash_arrays import source_list_digest
from verify_c_string_sources import syntax_tool, verify


def array_modules(link, row):
    key = row["archive"]
    files = row["modules"]
    if key in link.get("native_c_strings", {}):
        raise ValueError("supply the parent before the candidate C-string substitutions")
    with TemporaryDirectory() as tmp:
        directory = Path(tmp)
        hashes = {}
        def capture(archive, module, checksum, data):
            name = str(module)
            if name in hashes or archive != Path(key):
                raise ValueError("unexpected compiler source")
            hashes[name] = checksum.hex()
            if name in files:
                dst = directory / module
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(data)
        measure(link, inspect_module=capture, archive_pair=(cargo_origin(link, key), Path(key)))
        if (source_list_digest(hashes) != row["parent_sources_sha256"] or len(hashes) != row["compiler_selected_sources"]
                or not files.keys() <= hashes.keys()):
            raise ValueError("selected Rust sources differ from the whole-archive pilot")
        paths = json.dumps(sorted(files)).encode()
        def scan(tool):
            return json.loads(subprocess.check_output([syntax_tool(tool), directory], input=paths))
        edits = scan("c-string-literals")
        covered = static_array_edits(directory, edits, syntax_tool("static-array-spans"))
    if edits.keys() != files.keys() or {m: len(v) for m, v in edits.items()} != files:
        raise ValueError("literal inventory differs from the cold-compiled modules")
    return {module: len(edits) for module, edits in covered.items()}


def recover(link_file, whole, output, *, include_mixed=False, skip_empty=False):
    link = json.loads(link_file.read_bytes())
    row = json.loads((whole / "pilot.json").read_bytes())
    key = Path(row["archive"])
    if (link["binary"]["sha256"] != row["control_binary_sha256"] or digest(ROOT / key) != row["control_sha256"]
            or row["control_sha256"] != link["source_library_sha256"].get(str(key))
            or row["candidate_sha256"] == row["control_sha256"] or digest(whole / key.name) != row["candidate_sha256"]):
        raise ValueError("expected the differing whole archive and its original release")
    counts = array_modules(link, row)
    modules = {m: count for m, count in counts.items() if count == row["modules"][m]}
    summary = dict(array_modules=modules, literals=sum(modules.values()),
                   array_literals_in_mixed_modules=sum(counts.values()) - sum(modules.values()))
    if include_mixed:
        modules = counts
        summary.update(selected_literals=sum(modules.values()), selected_module_count=len(modules))
    print(json.dumps(summary, sort_keys=True), flush=True)
    if output is None:
        return
    if not modules or modules == row["modules"]:
        if skip_empty:
            return None
        raise ValueError("no proper nonempty subset of array initializers")
    if not output.exists():
        build(link_file, output, key, modules=sorted(modules), static_arrays=include_mixed)
    candidate = json.loads((output / "pilot.json").read_bytes())
    if (("static_array_selector_sha256" in candidate) != include_mixed or candidate["modules"] != modules or any(candidate[k] != row[k] for k in
            ("archive", "control_sha256", "control_binary_sha256", "parent_sources_sha256"))):
        raise ValueError("subset pilot changed its parent or selected modules")
    verify(link_file, output)
    result = dict(archive=str(key), whole_candidate_sha256=row["candidate_sha256"], candidate=candidate,
                  byte_identical=candidate["candidate_sha256"] == row["control_sha256"])
    with TemporaryDirectory(dir=output) as temp:
        staged = Path(temp) / "comparison.json"
        staged.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        staged.replace(output / "comparison.json")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path)
    parser.add_argument("whole", type=Path)
    parser.add_argument("--include-mixed", action="store_true", help="select only array edits within mixed modules, too")
    parser.add_argument("--output", type=Path, help="cold-build and verify the selected subset")
    args = parser.parse_args()
    recover(args.link, args.whole, args.output, include_mixed=args.include_mixed)
