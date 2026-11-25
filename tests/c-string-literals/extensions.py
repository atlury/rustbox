#!/usr/bin/env python3
"""Check a real eight-literal to 92-literal extension and reject loss of any earlier selection."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_linked_pointers import check_identical_layer, measure
from cargo_source_parent import cargo_origin
from verify_c_string_sources import check_extension


def rejects(action):
    try:
        action()
    except ValueError:
        return
    raise AssertionError("accepted an incompatible source or inventory")


def run(link):
    parent = json.loads(link.read_bytes())
    smaller = json.loads((ROOT / "evidence/e2fsprogs-mixed-array-c-strings.json").read_bytes())["comparison"]["candidate"]
    larger = json.loads((ROOT / "evidence/e2fsprogs-badblocks-literal-subsets.json").read_bytes())["best_verified_candidate"]
    field = "native_c_strings"
    key = smaller["archive"]
    pair = (cargo_origin(parent, key), Path(key))

    def selected(row):
        return {**parent, field: {key: row}}

    small, large = selected(smaller), selected(larger)
    before, after = [measure(stage, archive_pair=pair) for stage in (small, large)]
    check_identical_layer(small, large, before, after, field)
    assert before["all"]["raw_pointer_type_tokens"] - after["all"]["raw_pointer_type_tokens"] == 168
    assert after["all"]["as_ptr_calls"] - before["all"]["as_ptr_calls"] == 84
    for name in ("parent_sources_sha256", "syntax_tool_sha256", "control_sha256", "legacy_compiler"):
        rejects(lambda: check_extension(smaller, dict(larger, **{name: "changed"})))
    rejects(lambda: check_extension(larger, smaller))
    rejects(lambda: check_extension(larger, larger))
    missing = deepcopy(larger)
    del missing["modules"][next(iter(smaller["modules"]))]
    rejects(lambda: check_extension(smaller, missing))
    rejects(lambda: check_extension(smaller, dict(larger, static_array_selector_sha256="different")))
    wrong = deepcopy(after)
    wrong["all"]["raw_pointer_type_tokens"] -= 16
    rejects(lambda: check_identical_layer(small, large, before, wrong, field))
    print("Replayed both badblocks selections, verified 168 additional casts and rejected nine invalid extensions.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path)
    run(parser.parse_args().link)
