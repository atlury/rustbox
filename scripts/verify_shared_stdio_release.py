#!/usr/bin/env python3
"""Verify a byte-identical multicall release, rerun public dispatch and record the compiler inventory."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from check_cargo_private_inlines import LINK_REPORT, ROOT, digest
from rank_fixed_array_helpers import rank as fixed_arrays
from rank_foreign_declarations import rank as foreign_declarations
from rank_shared_applet_modules import rank as shared_modules, rank_tables
from test_inline_release import all_packages


def verify(previous, binary, replay_path, output, layer="shared_stdio_layouts"):
    stage, option, metric, summary_field = {
        "shared_scalar_ffi": ("scalar-ffi", "--verify-scalar-ffi-from", "scalar_ffi_deltas", "shared_declaration_deltas"),
        "closed_inline_groups": ("closed-inlines", "--verify-closed-inlines-from", "closed_inline_deltas", "private_helper_deltas"),
        "native_c_strings": ("native-c-strings", "--verify-native-c-strings-from", "native_c_string_conversions", "c_string_conversions"),
        "shared_stdio_layouts": ("shared-stdio", "--verify-shared-stdio-from", "shared_stdio_layout_deltas", "repeated_pointer_fields_removed"),
        "shared_ncurses_termtypes": ("ncurses-termtypes", "--verify-termtypes-from", "shared_ncurses_termtype_deltas", "repeated_pointer_fields_removed"),
        "shared_va_list_layouts": ("va-list-layouts", "--verify-va-list-from", "shared_va_list_layout_deltas", "repeated_pointer_fields_removed"),
    }[layer]
    output.mkdir()
    old, current = previous.read_bytes(), LINK_REPORT.read_bytes()
    parent, selected = json.loads(old), json.loads(current)
    saved = output / "release.json"
    saved.write_bytes(current)
    sha = digest(binary)
    previous_sha = sha256(old).hexdigest()
    replay_bytes = replay_path.read_bytes()
    replay = json.loads(replay_bytes)
    if (selected["binary"] != parent["binary"] or selected["binary"]["sha256"] != sha
            or replay["binary_sha256"] != sha or replay["link_report_sha256"] != previous_sha
            or replay["packages"] != dict.fromkeys(all_packages(), 0)):
        raise ValueError("the ELF, link map, parent or completed package suites differ")
    summary = json.loads((ROOT / "evidence/rustbox-multicall.json").read_bytes())
    if any(summary["binary"][key] != value for key, value in selected["binary"].items() if key in summary["binary"]):
        raise ValueError("published release summary differs from the selected executable")
    scripts = ROOT / "scripts"
    with (output / "inventory.json").open("wb") as stream:
        subprocess.run([sys.executable, "-B", scripts / "audit_linked_pointers.py", saved,
                        option, previous], stdout=stream, check=True)
    public = {}
    for name, tool in (("dispatch", "test_rustbox_multicall.sh"), ("batch_differential", "test_rustbox_batch_differential.sh")):
        log = output / (name + ".log")
        with log.open("wb") as stream:
            subprocess.run([scripts / tool], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=True,
                           env=dict(os.environ, RUSTBOX_MULTICALL_TEST_BINARY=str(binary)))
        actual = json.loads(log.read_bytes().splitlines()[-1])
        expected = summary[name]
        if any(actual[k] != expected[k] for k in actual) or actual["passed"] != actual["cases"]:
            raise ValueError(f"{name} coverage differs from the previously tested binary")
        public[name] = actual

    current_sha = sha256(current).hexdigest()
    inventory = json.loads((output / "inventory.json").read_bytes())
    reports = {
        "rustbox-linked-pointers": inventory,
        "rustbox-foreign-declaration-candidates": foreign_declarations(saved),
        "rustbox-fixed-array-candidates": fixed_arrays(saved),
        "rustbox-shared-module-candidates": shared_modules(saved, 20),
        "rustbox-static-name-tables": rank_tables(saved, 20),
        f"rustbox-{stage}-replays": {
            "binary_sha256": sha, "link_report_sha256": current_sha, "previous_link_report_sha256": previous_sha,
            "previous_replays_sha256": sha256(replay_bytes).hexdigest(), "packages": replay["packages"],
            "package_replay_basis": "identical ELF, link map, dynamic dependencies and archive inputs",
            summary_field: inventory[metric], **public},
    }
    with TemporaryDirectory(dir=ROOT / "evidence") as temp:
        staged = Path(temp)
        for name, report in reports.items():
            if (report["binary_sha256"], report["link_report_sha256"]) != (sha, current_sha):
                raise ValueError(f"{name} belongs to another release")
            (staged / (name + ".json")).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        if LINK_REPORT.read_bytes() != current or digest(binary) != sha:
            raise ValueError("release changed during verification")
        for path in staged.iterdir():
            path.replace(ROOT / "evidence" / path.name)
    print(f"{len(selected[layer])} identical archives, {public['batch_differential']['passed']} differential cases, ELF {sha}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("previous_link", type=Path)
    parser.add_argument("binary", type=Path)
    parser.add_argument("previous_replays", type=Path)
    parser.add_argument("new_directory", type=Path)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--shared-scalar-ffi", dest="layer", action="store_const", const="shared_scalar_ffi")
    selection.add_argument("--closed-inlines", dest="layer", action="store_const", const="closed_inline_groups")
    selection.add_argument("--native-c-strings", dest="layer", action="store_const", const="native_c_strings")
    selection.add_argument("--ncurses-termtypes", dest="layer", action="store_const", const="shared_ncurses_termtypes")
    selection.add_argument("--va-list-layouts", dest="layer", action="store_const", const="shared_va_list_layouts")
    parser.set_defaults(layer="shared_stdio_layouts")
    args = parser.parse_args()
    verify(args.previous_link.resolve(), args.binary.resolve(), args.previous_replays.resolve(), args.new_directory.resolve(),
           args.layer)
