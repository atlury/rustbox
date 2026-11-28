#!/usr/bin/env python3
"""Remove closed groups of unreferenced C layout types from multicall staticlib compiler inputs."""
# SPDX-License-Identifier: 0BSD
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess

from build_checked_errno import replay
from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from cargo_source_parent import cargo_origin, direct_crate
from check_cargo_private_inlines import ROOT, digest
from direct_source_pair import build_pair, direct_receipt, mounted_pair
from inline_source_layout import WHITESPACE
from prune_private_inlines import POINTER
from verify_c_string_sources import syntax_tool

SELECTOR = ROOT / "tools/private-inlines/src/bin/unused-c-types.rs"
MARKER = ".rustbox-unused-c-types"


def substitute(crate, sources, tool=None):
    tool = tool or syntax_tool("unused-c-types")
    rows = json.loads(subprocess.check_output([tool, crate], input=json.dumps(sorted(sources)).encode()))
    if not rows.keys() <= sources.keys():
        raise ValueError("unreferenced types outside compiler inputs")
    changes, kinds, removed = {}, Counter(), 0
    for name, sites in rows.items():
        data = bytearray((crate / name).read_bytes())
        previous = 0
        for ident, kind, start, end in sites:
            if not previous <= start < end <= len(data):
                raise ValueError(f"overlapping unused type declarations in {name}")
            declaration = data[start:end]
            if kind not in {"struct", "union", "type"} or ident.encode() not in declaration:
                raise ValueError(f"unexpected {kind} declaration in {name}")
            removed += len(POINTER.findall(declaration))
            data[start:end] = declaration.translate(WHITESPACE)
            kinds[kind] += 1
            previous = end
        changes[name] = bytes(data)
    return changes, dict(scanner_sha256=digest(SELECTOR), removed_declarations=dict(kinds),
                         changed_modules=len(changes), raw_pointer_types_removed=removed)


def replay_layer(parent, read_parent, row, tool):
    from build_scalar_ffi import replay_layer as replay_sources
    return replay_sources(parent, read_parent, row, tool, transform=substitute)


def trial(link, key, output=None):
    direct = direct_crate(cargo_origin(json.loads(link.read_bytes()), key)) is not None
    if output is None:
        return direct_receipt(link, key, substitute) if direct else replay(link, key, transform=substitute)
    if direct:
        build_pair(link, output, key, Path(__file__).name, ["--direct", key], substitute)
    else:
        stage_selected_archive(link, output, key, MARKER, Path(__file__).name, linux_scratch=True)
        replay(link, key, output, transform=substitute)
    return json.loads((output / "pilot.json").read_bytes())


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mounted", type=Path)
    p.add_argument("--direct")
    p.add_argument("--link", type=Path)
    p.add_argument("--archive")
    p.add_argument("--replay", action="store_true", help="verify a saved cold archive against the current sources")
    p.add_argument("--output", type=Path, help="cold-build and replay both archives")
    a = p.parse_args()
    if a.direct:
        mounted_pair(Path("/trial/release.json"), Path("/trial/result"), a.direct, substitute, allow_identical=True)
    elif a.mounted:
        compile_mounted_sources(a.mounted, substitute, MARKER, allow_identical=True)
    elif a.link and a.archive and a.output and a.replay:
        row = trial(a.link, a.archive)
        row["candidate_sha256"] = digest(a.output / Path(a.archive).name)
        if row != json.loads((a.output / "pilot.json").read_bytes()):
            raise ValueError("cold archive differs from the independent unused type replay")
        print(json.dumps(row, indent=2, sort_keys=True))
    elif a.link and a.archive and not a.replay:
        print(json.dumps(trial(a.link, a.archive, a.output), indent=2, sort_keys=True))
    else:
        p.error("supply a compiled release and archive")
