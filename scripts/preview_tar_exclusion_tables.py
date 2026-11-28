#!/usr/bin/env python3
"""Verify GNU tar's immutable name tables through both dispatch modes of the full multicall."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import json
from pathlib import Path

from check_cargo_private_inlines import ROOT, digest
from link_rustbox_multicall import namespace_tar_inputs
from preview_cargo_multicall import preview as preview_archive
from preview_tar_timespec import commands
from test_tar_exclusion_tables import PKG, exercise


def preview(link, log, pilot, output, *, name="exclusion"):
    qualified = json.loads((ROOT / f"evidence/tar-{name}-tables-pilot.json").read_bytes())
    row = qualified["archive"]
    def namespace(path, residues, release, stage):
        archive, objects, symbols, imports = namespace_tar_inputs(path, residues, release["acl_namespaced_symbols"], stage)
        if symbols != release["tar_namespaced_symbols"] or imports != release["tar_acl_imports"]:
            raise ValueError("GNU tar or ACL public symbols differ from the selected release")
        return archive, objects
    def compare(elf, stage):
        result = commands(elf, stage)
        programs = {cc:[PKG / "oracle" / (cc + "-root/usr/bin/tar")] for cc in ("gcc", "clang")}
        programs.update(applet=[stage / "applet/usr/bin/tar"], subcommand=[elf, "tar"])
        if any(digest(programs[cc][0]) != qualified["executable_sha256"][cc] for cc in ("gcc","clang")):
            raise ValueError("the canonical tar executables changed")
        if name == "combined-name":
            from test_tar_name_tables import exercise as combined
            observations = combined(programs, stage)
            for which, fields in (("argmatch", ("tables", "cases", "failed_options", "observations_sha256")),
                                  ("exclusions", ("profiles", "fixture_files"))):
                if any(observations[which][k] != qualified[which][k] for k in fields):
                    raise ValueError(f"{which} differed through the combined GNU tar multicall")
            count = observations["argmatch"]["cases"] + len(observations["exclusions"]["profiles"])
            return dict(result, combined_tables=observations, table_comparisons=len(programs)*count)
        if name == "argmatch":
            from test_tar_argmatch_tables import exercise as match_options
            observations = match_options(programs, stage)
            if any(observations[k] != qualified[k] for k in ("tables","cases","failed_options","observations_sha256")):
                raise ValueError("GNU tar option parsing differs through the public executable")
            return dict(result, argmatch=observations, argmatch_comparisons=len(programs)*observations["cases"])
        observations = exercise(programs, stage)
        if observations["profiles"] != qualified["profiles"] or observations["fixture_files"] != qualified["fixture_files"]:
            raise ValueError("archive members or public branch coverage changed")
        return dict(result, exclusions=observations, exclusion_comparisons=4*len(observations["profiles"]))
    preview_archive(link, log, pilot, output, row, namespace, compare)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("link","log","pilot","output"):
        p.add_argument(name, type=Path)
    modes = p.add_mutually_exclusive_group()
    modes.add_argument("--argmatch", dest="name", action="store_const", const="argmatch", help="qualify option parsing")
    modes.add_argument("--combined", dest="name", action="store_const", const="combined-name", help="qualify all seven tables")
    p.set_defaults(name="exclusion")
    a = p.parse_args()
    preview(a.link,a.log,a.pilot,a.output,name=a.name)
