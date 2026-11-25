#!/usr/bin/env python3
"""Exercise independently qualified parser archives together in one 499-name multicall."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import json
from pathlib import Path

from check_cargo_private_inlines import ROOT, digest
from preview_cargo_multicall import preview_link, qualified_inputs
from preview_checked_buffer import commands as buffer_commands, zstd_namespace
from preview_curl_month_array import namespace as curl_namespace
from preview_less_message_catalog import commands as less_commands, namespaced as less_namespace


def curl_commands(elf, stage):
    from preview_curl_checked_parsers import commands
    return commands(elf, stage)


def zstd_commands(elf, stage):
    return buffer_commands(elf, stage, "zstd")


PACKAGES = {
    "zstd": ("zstd-lorem-composed-archive.json", zstd_namespace, zstd_commands),
    "less": ("less-checked-message-catalog.json", less_namespace, less_commands),
    "curl": ("curl-checked-parser-archive.json", curl_namespace, curl_commands),
}


def compare(parent, log, output, pilots):
    if len(pilots) < 2:
        raise ValueError("select at least two checked packages")
    raw = parent.read_bytes()
    release = json.loads(raw)
    prepare_package = {}
    evidence = {}
    for name, pilot in pilots.items():
        filename, namespace, _ = PACKAGES[name]
        path = ROOT / "evidence" / filename
        proof = json.loads(path.read_bytes())["archive"]
        prepare_package[name] = qualified_inputs(release, pilot, proof, namespace)
        evidence[name] = digest(path)

    def prepare(which, directory):
        inputs, changed, packages = [], set(), {}
        for package, make in prepare_package.items():
            objects, replaced, metadata = make(which, directory)
            inputs.extend(objects)
            changed.update(replaced)
            packages[package] = metadata["archive_sha256"]
        return inputs, changed, dict(packages=packages)

    def exercise(elf, stage):
        results = {}
        for package in pilots:
            directory = stage / ("test-" + package)
            directory.mkdir()
            results[package] = PACKAGES[package][2](elf, directory)
        return dict(public=results, archive_evidence_sha256=evidence)

    preview_link(parent, raw, log, output, prepare, exercise)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("parent", "log", "output"):
        p.add_argument(arg, type=Path)
    for name in PACKAGES:
        p.add_argument("--" + name, type=Path, help="qualified archive directory")
    args = p.parse_args()
    compare(args.parent, args.log, args.output, {k: getattr(args, k) for k in PACKAGES if getattr(args, k)})
