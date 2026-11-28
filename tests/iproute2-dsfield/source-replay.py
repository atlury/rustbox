#!/usr/bin/env python3
"""Check DS field reuse against source changes that leave the input archive bytes unchanged."""
# SPDX-License-Identifier: GPL-2.0-or-later
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from preview_routing_protocols import check_dsfield_replay


class Replay(unittest.TestCase):
    def setUp(self):
        self.rank = json.loads((ROOT / "evidence/iproute2-dsfield-lz4-source-replay.json").read_bytes())
        self.batch = json.loads((ROOT / "evidence/iproute2-dsfield-archives.json").read_bytes())
        self.release = dict(binary={"sha256": self.rank["binary_sha256"]},
                            source_library_sha256={k: row["control_sha256"] for k, row in self.batch["verified"].items()})

    def check(self, rank):
        return check_dsfield_replay(rank, self.batch, self.release, self.rank["link_report_sha256"])

    def test_matching_inputs(self):
        self.assertEqual(self.check(self.rank), 4770)

    def test_stale_inputs(self):
        key = next(iter(self.rank["engines"]))
        for field in ("parent_sources_sha256", "candidate_sources_sha256", "helper_sha256", "control_archive_sha256"):
            with self.subTest(field=field):
                rank = deepcopy(self.rank)
                rank["engines"][key][field] = "0" * 64
                with self.assertRaises(ValueError):
                    self.check(rank)

    def test_missing_engine(self):
        self.rank["engines"].popitem()
        with self.assertRaises(ValueError):
            self.check(self.rank)


if __name__ == "__main__":
    unittest.main()
