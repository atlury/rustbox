#!/usr/bin/env python3
"""Reconstruct exactly the native C strings used in a cold Cargo archive, after existing layout changes."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from check_cargo_private_inlines import ROOT, digest
from check_e2fsprogs_dirhash_arrays import source_list_digest


def syntax_tool():
    if sys.platform.startswith("linux"):
        built = ROOT / "work/analysis/private-inlines-linux/release/c-string-literals"
        if built.is_file():
            return built
    target = ROOT / "work/analysis/syntax-tools-native"
    subprocess.run(["cargo", "build", "--locked", "--offline", "--release", "--manifest-path",
                    ROOT / "tools/private-inlines/Cargo.toml", "--bin", "c-string-literals",
                    "--target-dir", target], check=True, stdout=subprocess.DEVNULL)
    return target / "release/c-string-literals"


def replay(sources, read, row, tool):
    from build_c_string_literal_pilot import rewrite
    if (source_list_digest(sources) != row["parent_sources_sha256"] or len(sources) != row["compiler_selected_sources"]
            or not row["modules"] or not row["modules"].keys() <= sources.keys()):
        raise ValueError("literal receipt and parent compiler sources differ")
    with TemporaryDirectory() as folder:
        scratch = Path(folder)
        selected = set(row["modules"])
        if "legacy_compiler" in row:
            selected.add("lib.rs")
        for name in selected:
            path = Path(name)
            if path.is_absolute() or ".." in path.parts or path.suffix != ".rs":
                raise ValueError("invalid literal module in receipt")
            data = read(name)
            if sha256(data).hexdigest() != sources[name]:
                raise ValueError(f"unexpected literal input: {name}")
            dest = scratch / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        replacements, actual = rewrite(scratch, selected, tool, row.get("legacy_compiler"), sorted(row["modules"]))
    # Host and Linux scanner binaries can differ. Require identical generated
    # Rust source for every compiled module, including the untouched modules.
    for k in ("modules", "c_string_literals", "raw_pointer_types_removed", "raw_ffi_pointer_extractions"):
        if actual[k] != row[k]:
            raise ValueError(f"literal replay differs for {k}")
    after = {**sources, **{k: sha256(v).hexdigest() for k, v in replacements.items()}}
    if source_list_digest(after) != row["candidate_sources_sha256"]:
        raise ValueError("literal replacements differ from the cold-compiled archive")
    return replacements


def verify(link_path, pilot):
    from audit_linked_pointers import measure
    selection = json.loads(link_path.read_bytes())
    row = json.loads((pilot / "pilot.json").read_bytes())
    key = row["archive"]
    archive = Path(key)
    if (selection["source_library_sha256"].get(key) != row["control_sha256"]
            or digest(ROOT / archive) != row["control_sha256"] or digest(pilot / archive.name) != row["candidate_sha256"]):
        raise ValueError("archive selection or candidate binary differs")
    from cargo_source_parent import cargo_origin, row_origin
    origin = cargo_origin(selection, key)
    if row_origin(row) != str(origin):
        raise ValueError("literal receipt selected another Cargo target")
    if key in selection.get("native_c_strings", {}):
        selection["native_c_strings"] = {k: v for k, v in selection["native_c_strings"].items() if k != key}
    hashes, data = {}, {}
    def inspect(selected_archive, module, checksum, source):
        if selected_archive != archive or str(module) in hashes:
            raise ValueError("unexpected compiler input")
        hashes[str(module)] = checksum.hex()
        if str(module) in row["modules"] or ("legacy_compiler" in row and str(module) == "lib.rs"):
            data[str(module)] = source
    measure(selection, inspect_module=inspect, archive_pair=(origin, archive))
    replay(hashes, data.__getitem__, row, syntax_tool())
    print(f"Reproduced {row['c_string_literals']} C literals from {len(hashes)} checked compiler inputs.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path)
    parser.add_argument("pilot", type=Path)
    args = parser.parse_args()
    verify(args.link, args.pilot)
