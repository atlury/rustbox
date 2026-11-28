#!/usr/bin/env python3
"""Repeat the IPRoute2 comparisons on a saved multicall executable using a Linux-native snapshot."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from check_cargo_private_inlines import ROOT, digest
from preview_routing_protocols import commands, dsfield_commands


def expected_binary(previous, release=None):
    if release is None:
        return previous["candidate"]["sha256"]
    import stage_dsfield_archives as dsfield
    import stage_routing_protocol_archives as routing
    preceding = dsfield.parent_view(release)
    if "dsfield_public_comparisons" in previous:
        field = dsfield.FIELD
    else:
        field = routing.FIELD
    if field not in release or release["binary"]["sha256"] == previous["parent"]["sha256"]:
        raise ValueError("expected a release with the qualified IPRoute2 substitution")
    routing.parent_view(preceding)
    rows = release[field]
    archives = {Path(key).stem.removeprefix("lib").removesuffix("_audit"): row["candidate_sha256"]
                for key, row in rows.items()}
    if len(archives) != len(rows) or archives != previous["candidate"]["engine_archive_sha256"]:
        raise ValueError("selected engines differ from the qualified multicall preview")
    return release["binary"]["sha256"]


def check(elf, receipt, link=None):
    previous = json.loads(receipt.read_bytes())
    expected = expected_binary(previous, json.loads(link.read_bytes()) if link else None)
    if digest(elf) != expected:
        raise ValueError("the executable differs from the selected routing protocol executable")
    with TemporaryDirectory() as directory:
        exercise = dsfield_commands if "dsfield_public_comparisons" in previous else commands
        current = exercise(elf, Path(directory))
    validate_coverage(previous, current)
    return dict(current, elf_sha256=expected)


def verify_release(preview, release, inventory, observed, field, metric):
    sha = expected_binary(preview, release)
    measured = {key: delta["raw_pointer_type_tokens"] for key, delta in inventory[metric].items()}
    expected = {key: row["raw_pointer_types_removed"] for key, row in release[field].items()}
    if sha != observed["elf_sha256"] or sha != inventory["binary_sha256"] or measured != expected:
        raise ValueError("IPRoute2 compiler inputs or tested executable differ from the selected archives")
    validate_coverage(preview, observed)


def validate_coverage(previous, current):
    for key in ("public_names", "differential_driver_sha256", "routel_source_sha256"):
        if current[key] != previous[key]:
            raise ValueError(f"changed canonical input or test coverage: {key}")
    if "dsfield_public_comparisons" in previous:
        for key in ("dsfield_profiles", "dsfield_public_comparisons"):
            if current[key] != previous[key]:
                raise ValueError(f"DS field coverage differs for {key}")
    for cc in ("gcc", "clang-18"):
        before, after = previous["canonical"][cc], current["canonical"][cc]
        # Live route output can change between network namespaces. commands()
        # compares each run's status, stdout and stderr with its own oracle.
        for key in ("cases_per_mode", "modes", "canonical_sha256", "filter_status"):
            if before[key] != after[key]:
                raise ValueError(f"changed {cc} comparison or canonical build: {key}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("elf", type=Path)
    p.add_argument("receipt", type=Path)
    p.add_argument("--link", type=Path, help="bind a later release to the same qualified engine archives")
    p.add_argument("--mounted", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args()
    if args.mounted:
        print(json.dumps(check(args.elf, args.receipt, args.link), indent=2, sort_keys=True))
    else:
        receipt = Path("/work") / args.receipt.resolve().relative_to(ROOT)
        options = ["--link", Path("/work") / args.link.resolve().relative_to(ROOT)] if args.link else []
        if "dsfield_public_comparisons" in json.loads(args.receipt.read_bytes()):
            subprocess.run(["docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64",
                            "-v", f"{ROOT}:/work:ro", "-v", f"{args.elf.resolve()}:/candidate:ro",
                            "-v", "rustbox-iproute2-7.3.0:/rustbox-iproute2:ro",
                            "--tmpfs", "/etc/iproute2", "--tmpfs", "/usr/share/iproute2",
                            "-w", "/work", "rustbox-e2fsprogs:2026-11-24", "sh", "-ec",
                            'cp /candidate /tmp/rustbox && chmod 755 /tmp/rustbox && exec "$@"',
                            "test", "python3", "-B", "/work/scripts/test_routing_protocol_multicall.py",
                            "/tmp/rustbox", receipt, "--mounted", *options], check=True)
        else:
            subprocess.run([ROOT / "scripts/run_multicall_tool.sh", "python3", "-B",
                            "/work/scripts/test_routing_protocol_multicall.py", "/rustbox-test-elf/rustbox",
                            receipt, "--mounted", *options], check=True,
                           env=dict(os.environ, RUSTBOX_MULTICALL_TEST_BINARY=str(args.elf.resolve())))
