#!/usr/bin/env python3
"""Exercise source selection, archive provenance and rejection of stale routing parents."""
# SPDX-License-Identifier: GPL-2.0-or-later
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from cargo_source_parent import cargo_origin, pinned_parent
import stage_dsfield_archives as ds


class Selection(unittest.TestCase):
    def setUp(self):
        self.parent = ds.parent_build_link()
        self.selected = ds.select(self.parent)
        self.key, self.row = next(iter(self.selected[ds.FIELD].items()))

    def test_round_trip_and_compiler_provenance(self):
        self.assertEqual(ds.parent_view(self.selected), self.parent)
        records = self.selected[ds.FIELD]
        self.assertEqual(len(records), 18)
        for row in records.values():
            key = str(ds.candidate_path(row))
            origin = str(cargo_origin(self.selected, key))
            self.assertEqual(origin, row.get("rustc_archive", row.get("cargo_archive")))
            self.assertEqual(self.selected["source_library_sha256"][key], row["candidate_sha256"])
            compiler_key = "rustc_archive" if "rustc_archive" in row else "cargo_archive"
            later = {"archive": key, "control_sha256": row["candidate_sha256"], compiler_key: origin}
            self.assertEqual(pinned_parent(key, later), self.selected)

    def test_saved_executable_receipts(self):
        from test_routing_protocol_multicall import expected_binary
        receipt = json.loads((ROOT / "evidence/iproute2-dsfield-all-multicall.json").read_bytes())
        routing = json.loads((ROOT / "evidence/iproute2-routing-protocol-multicall.json").read_bytes())
        self.selected["binary"] = {"sha256": receipt["candidate"]["sha256"]}
        for prior in (receipt, routing):
            self.assertEqual(expected_binary(prior, self.selected), self.selected["binary"]["sha256"])
        with self.assertRaises(ValueError):
            expected_binary(receipt, self.parent)
        receipt["candidate"]["engine_archive_sha256"]["bridge"] = "0" * 64
        with self.assertRaises(ValueError):
            expected_binary(receipt, self.selected)

    def test_rejects_stale_parent_archive(self):
        self.parent["source_library_sha256"][self.key] = "0" * 64
        with self.assertRaises(ValueError):
            ds.select(self.parent)

    def test_rejects_newer_sources_with_identical_archive(self):
        self.parent["closed_inline_groups"] = {self.key: {"archive": self.key}}
        with self.assertRaises(ValueError):
            ds.select(self.parent)

    def test_rejects_stale_candidate(self):
        broken = deepcopy(self.selected)
        broken["source_library_sha256"][str(ds.candidate_path(self.row))] = "0" * 64
        with self.assertRaises(ValueError):
            ds.parent_view(broken)


if __name__ == "__main__":
    unittest.main()
