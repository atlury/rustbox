#!/usr/bin/env python3
"""Pack GNU Diffutils' four private help message catalogs and retain per-message gettext calls."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from hashlib import sha256
import json
from pathlib import Path

from build_checked_errno import replay
from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import ROOT, digest
from check_e2fsprogs_dirhash_arrays import source_list_digest
from packed_help_catalog import replace_table
from prune_private_inlines import POINTER

MARKER = ".rustbox-diffutils-help-catalogs"
CATALOGS = {
    "cmp": (9, "6bd6ada712ea5c40d79374cb20ff62df279b6aa607bef1b2e067e64e9dcb7d97", "9fc2b64cecfaa008fde27ec0ee177b8a17ac3b05d851e06e40f6db62e276d42c"),
    "diff": (69, "234166245fe5cfe33d4f4ba8b3b9f80b37acb8d50273e2ecc066347c4c47e3cb", "f89740750bda61c5fabc71ea26c6ea3a9e4f8623a1e765680e241ac8c559d13e"),
    "diff3": (20, "abae2dd564c6e35935157ce944de23139f896c982a41ee14136a07f56827bf0c", "b893b782f84193ab4eb6756b350f3c89ef4b89e3b54df761505721e75cba52b9"),
    "sdiff": (26, "1ef218d562c00745a6177872706079164c040e49a68a78c50dd69957fd0fa8b1", "62e1f9753eb2be18685aca5995ab418038b269442c54c56077d8ef56427bd1c4"),
}


def selection():
    rows = json.loads((ROOT / "evidence/mixed-array-c-string-utilities.json").read_bytes())["identical"]
    key, = [k for k in rows if Path(k).name.startswith("libdiffutils_")]
    return key, rows[key]


def prepare(link):
    key, row = selection()
    previous = link.get("native_c_strings", {})
    if (link["source_library_sha256"].get(key) != row["candidate_sha256"] or key not in link["shared_stdio_layouts"]
            or previous.get(key, row) != row):
        raise ValueError("expected Diffutils with the validated stdio layout and literal selection")
    link["native_c_strings"] = {**previous, key: row}
    return link


def substitute(crate, sources):
    _, row = selection()
    if source_list_digest(sources) != row["candidate_sources_sha256"]:
        raise ValueError("Diffutils compiler inputs differ from the reviewed literal selection")
    changed, tables = {}, {}
    head = b"""    let mut p: *const *const ::core::ffi::c_char = &raw const option_help_msgid
        as *const *const ::core::ffi::c_char;
    while !(*p).is_null() {"""
    tail = b"        p = p.offset(1);\n    }"
    removed = 0
    for name, (capacity, checksum, upstream_sha) in CATALOGS.items():
        module = "src/normalized_source/src/" + name + ".rs"
        original = (crate / module).read_bytes()
        if (sources[module] != checksum or sha256(original).hexdigest() != checksum
                or digest(ROOT / "work/upstream/diffutils-3.12/src" / (name + ".c")) != upstream_sha):
            raise ValueError("reviewed GNU Diffutils source differs for " + name)
        data, table = replace_table(original, b"option_help_msgid", capacity)
        start = data.index(head)
        end = data.index(tail, start)
        body = data[start + len(head):end]
        expected = 1 if name == "cmp" else 2
        if body.count(b"*p") != expected or body.count(b"dcgettext(") != 1:
            raise ValueError("unexpected message cursor consumers for " + name)
        body = body.replace(b"**p == 0", b"line.len() == 1").replace(b"**p != 0", b"line.len() > 1")
        if body.count(b"*p,") != 1:
            raise ValueError("expected one message ID argument")
        body = body.replace(b"*p,", b"line.as_ptr().cast::<::core::ffi::c_char>(),")
        data = data[:start] + b"    for line in OPTION_HELP.split_inclusive(|&byte| byte == 0) {" + body + b"    }" + data[end + len(tail):]
        changed[module] = data
        tables[name] = dict(**table, canonical_sha256=upstream_sha, parent_sha256=checksum, candidate_sha256=sha256(data).hexdigest())
        removed += len(POINTER.findall(original)) - len(POINTER.findall(data))
    return changed, dict(catalogs=tables, static_pointer_entries_removed=sum(r["static_pointer_entries_removed"] for r in tables.values()),
                         raw_pointer_types_removed=removed)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--link", type=Path)
    p.add_argument("--prepare-parent", type=Path)
    p.add_argument("--mounted", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--replay", action="store_true")
    a = p.parse_args()
    if a.mounted:
        compile_mounted_sources(a.mounted, substitute, MARKER, allow_identical=True)
    elif a.prepare_parent:
        print(json.dumps(prepare(json.loads(a.prepare_parent.read_bytes())), indent=2, sort_keys=True))
    elif a.link and a.replay:
        print(json.dumps(replay(a.link, selection()[0], a.output, transform=substitute), indent=2, sort_keys=True))
    elif a.link and a.output:
        stage_selected_archive(a.link, a.output, selection()[0], MARKER, Path(__file__).name)
    else:
        p.error("supply the parent release and a build destination or --replay")
