#!/usr/bin/env python3
"""Relink the qualified curl FTP or Zstd generator archive and exercise both multicall dispatch modes."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import json
from pathlib import Path
import shlex
import subprocess

from check_cargo_private_inlines import ROOT, digest
from link_rustbox_multicall import namespace_zstd_library
from preview_cargo_multicall import preview
from preview_curl_month_array import namespace as curl_namespace


def zstd_namespace(archive, residues, release, stage):
    mapped, symbols = namespace_zstd_library(archive, stage)
    if residues or release["zstd_namespaced_symbols"] != symbols:
        raise ValueError("Zstd linked symbols differ from the release")
    return mapped, []


def commands(elf, tmp, package):
    names = ["curl"] if package == "curl" else ["zstd", "zstdmt", "unzstd", "zstdcat", "zstdgrep", "zstdless"]
    results = {}
    for mode in ("applet", "subcommand"):
        directory = tmp / mode
        directory.mkdir()
        for name in names:
            path = directory / name
            if mode == "applet":
                path.symlink_to(elf)
            else:
                path.write_text("#!/bin/sh\nexec " + shlex.quote(str(elf)) + " " + name + ' "$@"\n')
                path.chmod(0o755)
        if package == "zstd":
            from test_zstd_lorem_commands import compare as compare_zstd
            results[mode] = compare_zstd(directory, directory)
        else:
            checks = {}
            pins = json.loads((ROOT / "evidence/curl-8.23.0-oracle.json").read_bytes())["binaries"]
            for cc in ("gcc", "clang"):
                binary = ROOT / "work/analysis/curl-8.23.0/oracle" / ("curl-" + cc)
                if digest(binary) != pins[cc]["sha256"]:
                    raise ValueError(f"canonical curl {cc} differs")
                report = directory / (cc + ".json")
                subprocess.run(["python3", ROOT / "tests/curl-oracle-differential.py", "--gcc", binary,
                                "--clang", directory / "curl", "--output", report], check=True, stdout=subprocess.DEVNULL)
                row = json.loads(report.read_bytes())
                if row["cases"] != row["passed"] or not row["passed"]:
                    raise ValueError("incomplete public curl comparison")
                checks[cc] = row["passed"]
            results[mode] = checks
    return dict(canonical=results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", choices=("curl", "zstd", "zstd-repeat-offsets"))
    for arg in ("parent", "log", "pilot", "output"):
        parser.add_argument(arg, type=Path)
    args = parser.parse_args()
    package = "curl" if args.package == "curl" else "zstd"
    if package == "zstd":
        receipt = "zstd-repeat-offsets-archive.json" if args.package == "zstd-repeat-offsets" else "zstd-lorem-archive.json"
        proof = json.loads((ROOT / "evidence" / receipt).read_bytes())["archive"]
        namespace = zstd_namespace
    else:
        proof = json.loads((ROOT / "evidence/curl-ftp-permissions-pilot.json").read_bytes())["public_wildcard"]
        namespace = curl_namespace
    preview(args.parent, args.log, args.pilot, args.output, proof, namespace,
            lambda elf, tmp: commands(elf, tmp, package))
