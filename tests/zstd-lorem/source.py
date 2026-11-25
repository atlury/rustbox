#!/usr/bin/env python3
"""Regenerate both native C-string layouts and check their incremental Zstd generator reductions."""
# SPDX-License-Identifier: BSD-3-Clause OR GPL-2.0-only
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_linked_pointers import measure
from build_c_string_literal_pilot import rewrite
from build_zstd_lorem import INPUTS, MODULE, substitute
from cargo_source_parent import cargo_origin
from prune_private_inlines import POINTER
from verify_c_string_sources import syntax_tool


def check(link_file):
    link = json.loads(link_file.read_bytes())
    key, = [key for key in link["source_library_sha256"] if key.endswith("/libzstd_1_5_7_normalized_audit.a")]
    checked = json.loads((ROOT / "evidence/zstd-lorem-generator.json").read_bytes())
    with TemporaryDirectory() as tmp:
        crate = Path(tmp)
        path = crate / MODULE
        path.parent.mkdir(parents=True)
        def collect(archive, module, checksum, data):
            if str(module) == MODULE:
                if archive != Path(key) or checksum.hex() != checked["control_module_sha256"] or path.exists():
                    raise ValueError("unexpected Zstd generator control")
                path.write_bytes(data)
        measure(link, inspect_module=collect, archive_pair=(cargo_origin(link, key), Path(key)))
        base = path.read_bytes()
        baseline, raw = substitute(crate, [MODULE])
        if raw["candidate_module_sha256"] != checked["candidate_module_sha256"]:
            raise ValueError("the original canonical Zstd pilot has changed")
        cases = {}
        inputs = {raw["control_module_sha256"]}
        for mode, arrays in (("arrays", syntax_tool("static-array-spans")), ("full", None)):
            path.write_bytes(base)
            changes, literals = rewrite(crate, [MODULE], syntax_tool(), modules=[MODULE], array_tool=arrays)
            path.write_bytes(changes[MODULE])
            updated, r = substitute(crate, [MODULE])
            inputs.add(r["control_module_sha256"])
            total = len(POINTER.findall(base)) - len(POINTER.findall(updated[MODULE]))
            if total != literals["raw_pointer_types_removed"] + r["raw_pointer_types_removed"]:
                raise ValueError("overlapping native casts counted twice")
            if mode == "arrays" and updated != baseline:
                raise ValueError("array-only selection changed the final generator source")
            cases[mode] = dict(literals=literals["c_string_literals"], native_casts_removed=literals["raw_pointer_types_removed"],
                               generator_casts_removed=r["raw_pointer_types_removed"], total=total,
                               native_sha256=r["control_module_sha256"], final_sha256=r["candidate_module_sha256"])
        if inputs != INPUTS:
            raise ValueError("unreplayed Zstd generator input in the converter")
        path.write_bytes(base + b"\n")
        try:
            substitute(crate, [MODULE])
        except ValueError:
            pass
        else:
            raise ValueError("converter accepted an unknown module")
    return dict(cases=cases, base_sha256=sha256(base).hexdigest(), release_sha256=link["binary"]["sha256"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path)
    print(json.dumps(check(parser.parse_args().link), indent=2, sort_keys=True))
