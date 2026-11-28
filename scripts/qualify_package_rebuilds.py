#!/usr/bin/env python3
"""Relink changed Cargo packages together and run every selected package's canonical GCC and Clang suites."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import fcntl
from pathlib import Path
import subprocess

from qualify_unused_type_batch import plan
from verify_unused_type_rebase import ROOT, digest, read, write_result


def mounted(path):
    return str(Path("/work") / path.resolve().relative_to(ROOT))


def qualify(control, previous, link_log, output, replacements, coreutils_volume):
    original = read(previous)
    if original["parent_link_sha256"] != digest(control):
        raise ValueError("package selection belongs to a different compiler control")
    output.mkdir(parents=True, exist_ok=True)
    archives = {key: ROOT / row["directory"] for key, row in original["archives"].items()}
    override = {}
    for path in replacements:
        receipt = read(path / "pilot.json")
        key = receipt["archive"]
        if key in override or receipt["candidate_sha256"] == receipt["control_sha256"]:
            raise ValueError("expected distinct, changed package archives")
        override[key] = path
    archives.update(override)
    selection = output / "selection.json"
    selected = plan(control, list(archives.values()))
    for key, row in original["archives"].items():
        if key not in override and row != selected["archives"][key]:
            raise ValueError(f"unchanged package receipt differs for {key}")
    if selection.exists() and read(selection) != selected:
        raise ValueError("output directory already holds a different compiler selection")
    write_result(selection, selected)
    docker = ["docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64",
              "-v", f"{ROOT}:/work:ro", "-v", f"{output.resolve()}:/results", "-w", "/work"]
    python = ["rustbox-e2fsprogs:2026-11-24", "python3", "-B"]
    def run(name, volumes, args):
        mounts = [flag for volume, mount in volumes for flag in ("-v", f"{volume}:{mount}:ro")]
        with (output / (name + ".log")).open("w") as log:
            subprocess.run([*docker, *mounts, *python, *args], check=True, stdout=log, stderr=subprocess.STDOUT)
    comparison, elf = (output / "linked" / name for name in ("comparison.json", "rustbox"))
    if not comparison.exists():
        run("link", [(coreutils_volume, "/rustbox-coreutils"), ("rustbox-util-linux-2.42.4", "/rustbox-util-linux")],
            ["scripts/qualify_unused_type_batch.py", "link", mounted(control), mounted(link_log),
             "/results/selection.json", "/results/linked"])
    linked = read(comparison)
    if (linked["candidate"]["sha256"] != digest(elf) or linked["selection_sha256"] != digest(selection)
            or linked["parent_link_report_sha256"] != digest(control)
            or linked["parent"]["sha256"] != selected["parent_binary_sha256"]):
        raise ValueError("physical link differs from the selected control or executable")
    for side, field in (("candidate","candidate_sha256"), ("parent","control_sha256")):
        if linked[side]["archive_sha256"] != {k: row["pilot"][field] for k,row in selected["archives"].items()}:
            raise ValueError(f"wrong {side} link inputs")
    commands = output / "commands.json"
    # A receipt is reusable only after checking the executable and selection below.
    if not commands.exists():
        volumes = [("rustbox-" + pkg, "/rustbox-" + name) for pkg,name in (
            ("gawk-5.4.0","gawk"), ("findutils-4.10.0","findutils"), ("kmod-34.3","kmod"), ("shadow-4.20.4","shadow"))]
        run("commands", volumes, ["scripts/check_unused_type_commands.py", "/results/linked/rustbox",
                                  "/results/selection.json", "/results/linked/comparison.json", "/results/commands.json"])
    checked = read(commands)
    suites = {Path(key).parts[2].split("-")[0] + "-" + cc for key in archives for cc in ("gcc","clang")}
    if (checked["binary_sha256"] != digest(elf) or checked["selection_sha256"] != digest(selection)
            or checked["side"] != "candidate" or set(checked["suites"]) != suites
            or any(s["passed"] <= 0 for s in checked["suites"].values())
            or checked["comparisons"] != sum(s["passed"] for s in checked["suites"].values())):
        raise ValueError("canonical suites differ from the selected packages or executable")
    write_result(output / "verified.json", dict(counts=selected["counts"], selection_sha256=digest(selection),
                 previous_selection_sha256=digest(previous), link=linked, commands=checked))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("control","previous","link_log","output"):
        parser.add_argument(field, type=Path)
    parser.add_argument("--replace", type=Path, action="append", required=True, help="cold archive directory to add or replace")
    parser.add_argument("--coreutils-volume", default="rustbox-dsfield-c0e71f2883d5f8a4")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.with_name(args.output.name + ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        qualify(args.control, args.previous, args.link_log, args.output, args.replace, args.coreutils_volume)
