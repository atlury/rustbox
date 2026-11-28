#!/usr/bin/env python3
"""Relink qualified bitmap engines and check the E2fsprogs multicall against both canonical builds."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import json
from pathlib import Path

from check_cargo_private_inlines import ROOT, digest
from preview_cargo_multicall import preview_link
from preview_e2p_error_names import compare_public_commands, engine_inputs
from test_e2fsprogs_bitmap_bits import compare_image


def compare_multicall(elf, stage, minimum_names):
    root = Path("/rustbox-e2fsprogs")
    commands = {cc: [root / ("stage-" + cc) / "sbin/e2fsck"] for cc in ("gcc", "clang-18")}
    alias = stage / "e2fsck"
    alias.symlink_to(elf)
    commands.update(applet=[alias], subcommand=[elf, "e2fsck"])
    return dict(filesystem=compare_image(stage, root / "stage-gcc/sbin", commands),
                public_commands=compare_public_commands(elf, stage, minimum_names))


def preview(parent, log, batch, output, receipt):
    raw = parent.read_bytes()
    release = json.loads(raw)
    proof = json.loads(receipt.read_bytes())
    inventory = ROOT / "evidence/e2fsprogs-bitmap-bits-selected-sources.json"
    expected = json.loads(inventory.read_bytes())
    baseline = json.loads((ROOT / "evidence/e2fsprogs-bitmap-multicall-control.json").read_bytes())
    if baseline["elf_sha256"] != release["binary"]["sha256"]:
        raise ValueError("unrecognized public bitmap control executable")
    if "archive" in proof:
        rows = {proof["archive"]["archive"]: proof}
        inventory_hash = proof["source_inventory_sha256"]
    else:
        rows = proof["archives"]
        inventory_hash = proof["inventory_sha256"]
        if rows.keys() != expected["archives"].keys():
            raise ValueError("the combined bitmap qualification is incomplete")
    if digest(parent) != proof["link_sha256"] or digest(inventory) != inventory_hash or proof["link_sha256"] != expected["link_sha256"]:
        raise ValueError("bitmap qualification belongs to a different compiler selection")
    selected = {}
    directories = {}
    for key, result in rows.items():
        stem = Path(key).stem
        engine = stem.removeprefix("lib").removesuffix("_audit")
        row = result["archive"]
        if (key != row["archive"] or expected["archives"][key]["archive_sha256"] != row["control_sha256"]
                or stem != f"lib{engine}_audit" or engine in selected
                or (result["comparisons"], result["memcheck_runs"]) != (393260, 1)):
            raise ValueError(f"unqualified engine {key}")
        selected[engine] = row
        directories[engine] = batch / stem
    if "e2fsck" not in selected:
        raise ValueError("the bitmap multicall comparison requires the qualified e2fsck engine")

    def exercise(elf, stage):
        actual = compare_multicall(elf, stage, len(selected))
        if any(actual[k] != baseline[k] for k in ("filesystem", "public_commands")):
            raise ValueError("bitmap multicall differs from the qualified public control")
        return dict(actual, archives=sorted(selected),
                    archive_evidence_sha256=digest(receipt))

    preview_link(parent, raw, log, output, engine_inputs(release, selected, directories), exercise)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("parent", "log", "batch", "output", "receipt"):
        p.add_argument(arg, type=Path)
    a = p.parse_args()
    preview(a.parent, a.log, a.batch, a.output, a.receipt)
