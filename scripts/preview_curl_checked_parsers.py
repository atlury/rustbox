#!/usr/bin/env python3
"""Exercise all three checked curl readers in the saved complete Linux multicall link."""
# SPDX-License-Identifier: curl
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from check_cargo_private_inlines import ROOT
from preview_cargo_multicall import preview
from preview_checked_buffer import commands as public_commands
from preview_curl_month_array import commands as calendar_commands, namespace


def commands(elf, stage):
    result = public_commands(elf, stage, "curl")
    utc = int(datetime(2001, 1, 5, 13, 14, 15, tzinfo=timezone.utc).timestamp())
    offsets = {"A": -1, "JST": -9, "NT": 11, "UT": 0, "NZDT": -13, "WAST": -7, "IDLW": 12}
    dates = [(f"Fri, 05 Jan 2001 13:14:15 {zone}", utc + hours * 3600) for zone, hours in offsets.items()]
    result.update(calendar_commands(elf, stage, dates))
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("parent", "log", "pilot", "output"):
        p.add_argument(name, type=Path)
    args = p.parse_args()
    row = json.loads((ROOT / "evidence/curl-checked-parser-archive.json").read_bytes())["archive"]
    preview(args.parent, args.log, args.pilot, args.output, row, namespace, commands)
