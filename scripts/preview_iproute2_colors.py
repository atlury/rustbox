#!/usr/bin/env python3
"""Verify qualified IPRoute2 terminal palettes in the complete Linux multicall."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess

from check_cargo_private_inlines import ROOT, digest
from link_rustbox_multicall import IPROUTE2_PROGRAMS
from preview_cargo_multicall import preview_link
from preview_routing_protocols import commands, qualified_engines


def color_commands(elf, stage):
    results = commands(elf, stage)
    baseline = json.loads((ROOT / "evidence/iproute2-color-palette-baseline.json").read_bytes())
    profiles = {}
    for background in ("1;0", "0;7"):
        env = dict(os.environ, LC_ALL="C", COLORFGBG=background)
        env.pop("NO_COLOR", None)
        for opts in (("-c",), ("-c=auto",), ("-c=never",), ("-j", "-c")):
            name = background + "/" + " ".join(opts)
            args = ["ip", *opts, "-br", "address", "show", "dev", "lo"]
            for cc in ("gcc", "clang-18"):
                path = Path("/rustbox-iproute2/programs-" + cc) / "ip"
                expected = subprocess.run(args, executable=path, env=env, capture_output=True, check=True, timeout=30)
                checksum = sha256(expected.stdout).hexdigest()
                if expected.stderr or checksum != baseline["public"][name]:
                    raise ValueError(f"canonical loopback output differs for {cc} {name}")
                for command, binary in ((args, stage / "applets/ip"), ([elf, *args], elf)):
                    actual = subprocess.run(command, executable=binary, env=env, capture_output=True, check=True, timeout=30)
                    if actual.stdout != expected.stdout or actual.stderr != expected.stderr:
                        raise ValueError(f"loopback colors differ for {command} {name}")
                profiles[name] = checksum
    if profiles != baseline["public"]:
        raise ValueError("incomplete public palette coverage")
    return dict(results, palette_profiles=profiles, palette_command_comparisons=4 * len(profiles))


def preview(parent, log, batch, output, first):
    raw = parent.read_bytes()
    release = json.loads(raw)
    name = "first-archives" if first else "archives"
    evidence = ROOT / f"evidence/iproute2-color-palette-{name}.json"
    report = json.loads(evidence.read_bytes())
    selected = report["engines"]
    if report["link_report_sha256"] != sha256(raw).hexdigest():
        raise ValueError("palette archives belong to a different parent")

    def resolve(engine, key, expected):
        folder = batch / engine
        compared = json.loads((folder / "comparison.json").read_bytes())
        row = compared["archive"]
        if (compared != selected[key] or row != json.loads((folder / "compiled/pilot.json").read_bytes())
                or row["archive"] != key or row["control_sha256"] != expected
                or row["control_binary_sha256"] != release["binary"]["sha256"]):
            raise ValueError(f"palette tests or source selection changed for {engine}")
        return folder / "compiled" / Path(key).name, row["candidate_sha256"]

    prepare = qualified_engines(release, selected, ("ip", "bridge") if first else IPROUTE2_PROGRAMS, resolve)
    def exercise(elf, stage):
        return dict(color_commands(elf, stage), archive_evidence_sha256=digest(evidence))
    preview_link(parent, raw, log, output, prepare, exercise)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("parent", "log", "batch", "output"):
        p.add_argument(arg, type=Path)
    p.add_argument("--first-archives", action="store_true")
    args = p.parse_args()
    preview(args.parent, args.log, args.batch, args.output, args.first_archives)
