#!/usr/bin/env python3
"""Compile device-group lookups with the release bridge engine's direct rustc recipe."""
# SPDX-License-Identifier: GPL-2.0-or-later
import json
from pathlib import Path
import sys

from build_group_names import substitute
from build_iproute2_bridge_address_protocols import BRIDGE
from cargo_source_parent import cargo_origin
from direct_source_pair import build_pair, direct_receipt, mounted_pair


def check_bridge(link, key):
    if cargo_origin(json.loads(link.read_bytes()), key) != BRIDGE:
        raise ValueError("unexpected bridge source origin")


def bridge_receipt(link, key, transform=substitute):
    check_bridge(link, key)
    return direct_receipt(link, key, transform)


def build(link, output, key):
    check_bridge(link, key)
    build_pair(link, output, key, Path(__file__).name, [key], substitute)


if __name__ == "__main__":
    key, = sys.argv[1:]
    link = Path("/trial/release.json")
    check_bridge(link, key)
    mounted_pair(link, Path("/trial/result"), key, substitute, allow_identical=False)
