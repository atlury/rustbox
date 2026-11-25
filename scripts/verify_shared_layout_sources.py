#!/usr/bin/env python3
"""Replay shared ABI declarations from every selected compiler input and verify the cold-built archive."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from audit_linked_pointers import measure
from cargo_source_parent import cargo_origin
from check_cargo_private_inlines import ROOT, digest
from check_e2fsprogs_dirhash_arrays import source_list_digest
from prune_private_inlines import POINTER


def verify(link_file, pilot, kind):
    if kind == "termtype":
        from build_ncurses_termtype_layouts import substitute
    else:
        from build_va_list_layout_pilot import substitute
    raw = link_file.read_bytes()
    release = json.loads(raw)
    row = json.loads((pilot / "pilot.json").read_bytes())
    archive = Path(row["archive"])
    if (row["control_binary_sha256"] != release["binary"]["sha256"]
            or release["source_library_sha256"].get(str(archive)) != row["control_sha256"]
            or digest(ROOT / archive) != row["control_sha256"] or digest(pilot / archive.name) != row["candidate_sha256"]):
        raise ValueError("archive or source release differs from its compiler receipt")
    with TemporaryDirectory() as tmp:
        crate = Path(tmp)
        hashes = {}
        def copy(selected, module, checksum, data):
            if archive != selected or str(module) in hashes:
                raise ValueError("unexpected or repeated compiler input")
            dest = crate / module
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            hashes[str(module)] = checksum.hex()
        measure(release, inspect_module=copy, archive_pair=(cargo_origin(release, str(archive)), archive))
        if len(hashes) != row["compiler_selected_sources"] or source_list_digest(hashes) != row["parent_sources_sha256"]:
            raise ValueError("compiler input set differs from the cold build")
        replacements, facts = substitute(crate, hashes)
        observed = 0
        for name, data in replacements.items():
            old = (crate / name).read_bytes()
            delta = len(POINTER.findall(old)) - len(POINTER.findall(data))
            expected = (9 * sum(name in group for group in facts["reexporting_modules"].values())
                        if kind == "termtype" else 2)
            if delta != expected or old.count(b"\n") != data.count(b"\n"):
                raise ValueError(f"unexpected delta in {name}")
            observed += delta
            hashes[name] = sha256(data).hexdigest()
        if (observed != facts["raw_pointer_types_removed"] or any(row[k] != v for k, v in facts.items()) or source_list_digest(hashes) != row["candidate_sources_sha256"]
                or link_file.read_bytes() != raw):
            raise ValueError("reconstructed provider, module or compiler input hashes differ")
    print(f"Verified {len(replacements)} changed modules, {row['compiler_selected_sources']} compiler inputs, "
          f"byte-identical archive={row['candidate_sha256'] == row['control_sha256']}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path)
    parser.add_argument("pilot", type=Path)
    parser.add_argument("--kind", choices=("va-list", "termtype"), required=True)
    args = parser.parse_args()
    verify(args.link, args.pilot, args.kind)
