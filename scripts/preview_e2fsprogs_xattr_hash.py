#!/usr/bin/env python3
"""Relink the qualified xattr hash archives and exercise both public debugfs dispatch modes."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import json
from pathlib import Path

from check_cargo_private_inlines import ROOT, digest
from preview_cargo_multicall import preview_link
from preview_e2p_error_names import compare_public_commands, engine_inputs
from test_e2fsprogs_xattr_hash import debugfs_images


def public(elf, stage):
    image = debugfs_images(stage, multicall=elf, oracle_root=Path("/rustbox-e2fsprogs"))
    tests = compare_public_commands(elf, stage, 28)
    return dict(filesystem=image, public_commands=tests)


def preview(link, log, batch, output, receipt):
    raw = link.read_bytes()
    release = json.loads(raw)
    proof = json.loads(receipt.read_bytes())
    inventory = ROOT / "evidence/e2fsprogs-xattr-hash-sources.json"
    expected = json.loads(inventory.read_bytes())
    known = json.loads((ROOT / "evidence/e2fsprogs-xattr-hash-multicall-control.json").read_bytes())
    if (proof["link_sha256"] != digest(link) or expected["link_sha256"] != proof["link_sha256"]
            or proof["inventory_sha256"] != digest(inventory) or known["elf_sha256"] != release["binary"]["sha256"]):
        raise ValueError("the xattr receipts do not match the chosen multicall parent")
    if "archived_results" in proof:
        rows = proof["archived_results"]
        if len(rows) != 1:
            raise ValueError("expected an individual archive receipt")
    else:
        rows = proof["archives"]
        if rows.keys() != expected["archives"].keys():
            raise ValueError("incomplete xattr archive selection")
    selected = {}
    directories = {}
    for key, result in rows.items():
        stem = Path(key).stem
        engine = stem.removeprefix("lib").removesuffix("_audit")
        row = result["archive"]
        if (key != row["archive"] or expected["archives"][key]["archive_sha256"] != row["control_sha256"]
                or (result["comparisons"], result["memcheck_runs"]) != (280576, 1)
                or result["fingerprint"] != "31150d9301677b0d" or engine in selected or stem != f"lib{engine}_audit"):
            raise ValueError(f"unqualified xattr engine {key}")
        selected[engine] = row
        directories[engine] = batch / stem
    if "debugfs" not in selected:
        raise ValueError("the tested debugfs must use the qualified candidate archive")

    def exercise(elf, stage):
        result = public(elf, stage)
        if any(result[k] != known[k] for k in result):
            raise ValueError("xattr multicall differs from its verified control")
        return dict(result, archives=sorted(selected), archive_evidence_sha256=digest(receipt))

    preview_link(link, raw, log, output, engine_inputs(release, selected, directories), exercise)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("link", "log", "batch", "output", "receipt"):
        p.add_argument(name, type=Path)
    a = p.parse_args()
    preview(a.link, a.log, a.batch, a.output, a.receipt)
