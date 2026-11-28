"""Bind a changed unused-type archive to its ranked sources and full multicall relink."""
# SPDX-License-Identifier: GPL-2.0-or-later
import json
from pathlib import Path

from build_unused_c_types import SELECTOR
from check_cargo_private_inlines import digest
from preview_cargo_multicall import preview


def compare_ranked(link, log, source_link, ranking, pilot, output, package, namespaced, commands):
    inventory = json.loads(ranking.read_bytes())
    row = json.loads((pilot / "pilot.json").read_bytes())
    key = row["archive"]
    source = json.loads(source_link.read_bytes())
    if (digest(source_link) != inventory["link_sha256"] or digest(SELECTOR) != inventory["scanner_sha256"]
            or row["control_binary_sha256"] != source["binary"]["sha256"]
            or inventory["binary_sha256"] != row["control_binary_sha256"]
            or source["source_library_sha256"][key] != row["control_sha256"]
            or Path(key).parts[2] != package or row["raw_pointer_types_removed"] <= 0
            or any(row.get(k) != v for k, v in inventory["archives"][key].items())):
        raise ValueError(f"{package} candidate differs from the ranked compiler inputs")
    def exercise(elf, stage):
        return {**commands(elf, stage), "pilot": row, "ranking_sha256": digest(ranking),
                "source_link_sha256": inventory["link_sha256"]}
    preview(link, log, pilot, output, row, namespaced, exercise)
