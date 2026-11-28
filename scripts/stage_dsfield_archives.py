#!/usr/bin/env python3
"""Stage the 18 tested IPRoute2 DS field implementations after the routing table selection."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from build_dsfield_names import build
from check_cargo_private_inlines import ROOT, digest
import stage_routing_protocol_archives as routing

FIELD = "iproute2_dsfield_names"
EVIDENCE = ROOT / "evidence/iproute2-dsfield-archives.json"
QUALIFICATION = {"canonical_inputs", "driver_sha256", "memcheck_runs", "oracle_compilers", "profiles", "public_oracle_sha256"}


def candidate_path(row):
    parent = Path(row["archive"])
    checksum = row["candidate_sha256"]
    if (parent.is_absolute() or ".." in parent.parts or parent.parent.parent.name != "routing-protocols"
            or parent.parent.name != row["control_sha256"] or len(checksum) != 64
            or any(c not in "0123456789abcdef" for c in checksum)):
        raise ValueError("expected a pinned routing archive and DS field digest")
    return parent.parents[2] / "dsfield-names" / checksum / parent.name


def pinned():
    rows = json.loads(EVIDENCE.read_bytes())["verified"]
    return {k: {f: v for f, v in r.items() if f not in QUALIFICATION} for k, r in rows.items()}


def select(parent):
    if FIELD in parent:
        raise ValueError("DS field archives already selected")
    routing.parent_view(parent)
    rows = pinned()
    previous = {str(routing.candidate_path(r)): r for r in parent.get(routing.FIELD, {}).values()}
    if previous.keys() != rows.keys() or len(rows) != 18:
        raise ValueError("DS field readers require all 18 qualified routing engines")
    hashes = parent["source_library_sha256"].copy()
    for key, row in rows.items():
        new = str(candidate_path(row))
        if (row["archive"] != key or previous[key]["candidate_sources_sha256"] != row["parent_sources_sha256"]
                or hashes.pop(key, None) != row["control_sha256"] or new in hashes):
            raise ValueError(f"unexpected routing parent for {key}")
        for layer in ("native_c_strings", "shared_stdio_layouts", "shared_va_list_layouts", "shared_ncurses_termtypes",
                      "closed_inline_groups", "shared_scalar_ffi"):
            if key in parent.get(layer, {}):
                raise ValueError(f"DS field archive requires recompilation after {layer} on {key}")
        hashes[new] = row["candidate_sha256"]
    return dict(parent, source_library_sha256=hashes, **{FIELD: rows})


def parent_view(link):
    if FIELD not in link:
        return link
    hashes = link["source_library_sha256"].copy()
    rows = link[FIELD]
    if rows != pinned():
        raise ValueError("DS field records differ from the verified compiler receipts")
    for key, row in rows.items():
        if key in hashes or hashes.pop(str(candidate_path(row)), None) != row["candidate_sha256"]:
            raise ValueError(f"missing or ambiguous DS field archive for {key}")
        hashes[key] = row["control_sha256"]
    parent = dict(link, source_library_sha256=hashes)
    del parent[FIELD]
    if select(parent) != link:
        raise ValueError("cannot restore the DS field source parent")
    return parent


def parent_build_link():
    parent = routing.select(routing.parent_build_link())
    parent["binary"] = {"sha256": json.loads(EVIDENCE.read_bytes())["binary_sha256"]}
    return parent


def prepare(link, sources):
    from preview_routing_protocols import check_dsfield_replay
    from rank_routing_protocols import rank
    raw = link.read_bytes()
    parent = json.loads(raw)
    selected = select(parent)
    historical = EVIDENCE.read_bytes()
    qualified = json.loads(historical)
    ranking = rank(link, dsfield=True)
    total = check_dsfield_replay(ranking, qualified, parent, sha256(raw).hexdigest())
    for key, row in qualified["verified"].items():
        path = ROOT / candidate_path(row)
        if digest(ROOT / key) != row["control_sha256"]:
            raise ValueError(f"unexpected linked archive for {key}")
        routing.install_qualified(link, sources, row, path, QUALIFICATION, ranking["binary_sha256"], build)
    if link.read_bytes() != raw or EVIDENCE.read_bytes() != historical or parent_view(selected) != parent:
        raise ValueError("source selection changed during DS field preparation")
    return dict(link_report_sha256=ranking["link_report_sha256"], qualified_batch_sha256=sha256(historical).hexdigest(),
                raw_pointer_types_removed=total, archives={k: str(candidate_path(row)) for k, row in selected[FIELD].items()})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path, nargs="?")
    parser.add_argument("--built", type=Path, help="reuse cold-built engine archives from the oracle batch")
    args = parser.parse_args()
    with TemporaryDirectory() as directory:
        link = args.link
        if link is None:
            link = Path(directory) / "parent.json"
            link.write_text(json.dumps(parent_build_link(), sort_keys=True))
        print(json.dumps(prepare(link, args.built), sort_keys=True, indent=2))
