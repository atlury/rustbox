#!/usr/bin/env python3
"""Convert the four byte-valued blank tests in the shared GNU Inetutils argp formatter."""
# SPDX-License-Identifier: 0BSD
import argparse
from hashlib import sha256
import json
from pathlib import Path

from build_checked_errno import replay
from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import ROOT, digest
from prune_private_inlines import POINTER
from rank_ctype_bytes import DECL, HELPER, matches, selected_helper

MODULE = "src/lib/argp_fmtstream.rs"
CANONICAL = ROOT / "work/upstream/inetutils-2.8/lib/argp-fmtstream.c"
MARKER = ".rustbox-argp-ctype"
# Five compiled spellings cover the 26 Inetutils engines in the stdio release.
INPUTS = {
    "0c1c3af41800760d2f126eb32ecb9ab6f6de09fae85a7c649701f063e93140d1",
    "91548511fe1ec3e8a8810a8ec85e7b8c90ff92a0567fa494c7010c3ad8ce71ac",
    "55f378c51c3f9df5ca4468e9460a0c3f98a8dc256c959a75d858f5728b327613",
    "b2af167ed9b8b0a8f55d2af4f349ca45d466c31804b9357875eb02dfc678052e",
    "486da56654fd63a99721cb50220378c35988f05dd53f23fed3c8728df0a9d4eb",
}


def substitute(crate, sources):
    data = (crate / MODULE).read_bytes()
    old = sha256(data).hexdigest()
    if (old not in INPUTS or old != sources[MODULE]
            or digest(CANONICAL) != "5bf0c4228cdedb5c8ccf1217f0ed40f5a3994e9f5f1a1716ef2b52d6a0e71393"
            or CANONICAL.read_bytes().count(b"isblank ((unsigned char) *p)") != 4):
        raise ValueError("unknown GNU formatter source")
    sites = matches(data)
    if (len(sites) != 4 or any(m["flag"] != b"blank" or m["value"] != b"*p" for m in sites)
            or data.count(b"__ctype_b_loc") != 5 or data.count(DECL) != 1):
        raise ValueError("expected four unsigned-byte classifications and one declaration")
    for site in reversed(sites):
        edit = b"crate::rustbox_ctype::blank(*p as u8)" + b"\n" * site[0].count(b"\n")
        data = data[:site.start()] + edit + data[site.end():]
    data = data.replace(DECL, b"")
    lib = (crate / "lib.rs").read_bytes()
    if b"rustbox_ctype" in lib or b"__ctype_b_loc" in data:
        raise ValueError("unexpected remaining formatter symbol")
    changed = {MODULE: data, "lib.rs": lib + b"\n" + selected_helper("blank")}
    removed = sum(len(POINTER.findall((crate / k).read_bytes())) - len(POINTER.findall(v)) for k, v in changed.items())
    if removed != 2:
        raise ValueError("unexpected number of raw pointer declarations")
    return changed, dict(module=MODULE, control_module_sha256=old, candidate_module_sha256=sha256(data).hexdigest(),
                         helper_sha256=digest(HELPER), canonical_sha256=digest(CANONICAL),
                         raw_pointer_types_removed=removed, ctype_table_reads_removed=4)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mounted", type=Path)
    p.add_argument("--link", type=Path)
    p.add_argument("--engine")
    p.add_argument("--output", type=Path)
    p.add_argument("--replay", action="store_true")
    a = p.parse_args()
    if a.mounted:
        compile_mounted_sources(a.mounted, substitute, MARKER, allow_identical=True)
    elif a.link and a.engine:
        keys = json.loads(a.link.read_bytes())["source_library_sha256"]
        key, = [k for k in keys if "/inetutils-2.8/" in k and Path(k).name == "lib" + a.engine + "_audit.a"]
        if a.replay:
            print(json.dumps(replay(a.link, key, a.output, transform=substitute), indent=2, sort_keys=True))
        elif a.output:
            stage_selected_archive(a.link, a.output, key, MARKER, Path(__file__).name)
        else:
            p.error("supply an empty archive destination or --replay")
    else:
        p.error("supply a link and engine")
