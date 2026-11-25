#!/usr/bin/env python3
"""Bind the packed LZ4 archive to the complete tested native-string and stdio sources."""
# SPDX-License-Identifier: GPL-2.0-or-later
from copy import deepcopy
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from cargo_source_parent import cargo_origin, pinned_parent
from lz4_dictionary_archive import KEY, parent_manifests, selected_link, selection
from test_lz4_dictionary_multicall import check as check_executable


def rejected(function, value):
    try:
        function(value)
    except (ValueError, KeyError):
        return
    raise AssertionError("accepted inconsistent dictionary selection")


def main():
    record = selection.pinned()
    row = record["pilot"]
    path = str(selection.candidate_path(row))
    proof = dict(archive=path, cargo_archive=KEY, control_sha256=row["candidate_sha256"])
    parent = {field: {KEY: value} for field, value in record["parent_receipts"].items()}
    parent["source_library_sha256"] = {KEY: row["control_sha256"]}
    parent["other_package"] = {"unrelated": 17}
    link = selected_link(parent)
    assert selection.parent_view(link) == parent
    assert str(cargo_origin(link, path)) == KEY
    minimal = pinned_parent(path, proof)
    for field, value in link.items():
        if field != "other_package":
            assert minimal[field] == value
    with TemporaryDirectory() as temp:
        directory = Path(temp)
        binary = directory / "wrong-elf"
        binary.write_bytes(b"unrelated")
        for source in (parent, link):
            manifest_path = directory / "selection.json"
            manifest_path.write_text(json.dumps(dict(source, binary={"sha256": "0" * 64})))
            rejected(lambda manifest: check_executable(manifest, binary), manifest_path)
        for routing, count in ((False, 1), (True, 19), (False, 1)):
            parent_manifests(directory, routing=routing)
            native = json.loads((directory / "native_c_strings.json").read_bytes())
            stdio = json.loads((directory / "shared_stdio_layouts.json").read_bytes())
            assert len(stdio) == 1 and len(native) == count
            assert stdio[KEY]["pilot"] == record["parent_receipts"]["shared_stdio_layouts"]
            assert native[KEY]["pilot"] == record["parent_receipts"]["native_c_strings"]
            assert native[KEY]["parent_receipts"] == dict(stdio[KEY]["parent_receipts"], shared_stdio_layouts=stdio[KEY]["pilot"])
    rejected(selected_link, link)
    for field in record["parent_receipts"]:
        bad = deepcopy(parent)
        del bad[field][KEY]
        rejected(selected_link, bad)
    for field in ("shared_va_list_layouts", "shared_ncurses_termtypes"):
        rejected(selected_link, dict(parent, **{field: {KEY: {}}}))
    rejected(selected_link, dict(parent, source_library_sha256={KEY: "0" * 64}))
    rejected(selected_link, dict(parent, source_library_sha256={**parent["source_library_sha256"], path: row["candidate_sha256"]}))
    rejected(selection.parent_view, dict(link, source_library_sha256={path: "0" * 64}))
    bad = deepcopy(link)
    bad[selection.field]["pilot"]["candidate_sources_sha256"] = "0" * 64
    rejected(selection.parent_view, bad)
    print(json.dumps(dict(parent_receipts=len(record["parent_receipts"]), pointer_types_removed=row["raw_pointer_types_removed"],
                          compiler_inputs=row["compiler_selected_sources"], archive=row["candidate_sha256"])))


if __name__ == "__main__":
    main()
