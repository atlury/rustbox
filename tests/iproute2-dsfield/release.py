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

    def test_earlier_public_interfaces_use_final_archive(self):
        from iproute2_address_protocol_archive import control_view
        from iproute2_route_name_archives import additional_lookup_records, lookup_records, netlink_control_view, routing_lookup_pair
        for view in (control_view, netlink_control_view):
            self.assertEqual(view(self.selected), view(self.parent))
        copies = additional_lookup_records(self.selected)
        self.assertEqual(len(copies), 17)
        for origin, row in lookup_records(self.selected).items():
            actual, before, after = routing_lookup_pair(self.selected, origin)
            self.assertEqual((actual, before, after), (row, ROOT / row["archive"], ROOT / ds.candidate_path(row)))
            if origin in copies:
                self.assertEqual(copies[origin]["candidate_sha256"], row["candidate_sha256"])

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

    def test_release_verification_checks_each_engine_and_tested_elf(self):
        from test_routing_protocol_multicall import verify_release
        preview = json.loads((ROOT / "evidence/iproute2-dsfield-all-multicall.json").read_bytes())
        sha = preview["candidate"]["sha256"]
        self.selected["binary"] = {"sha256": sha}
        observed = dict(preview, elf_sha256=sha)
        measured = {k: {"raw_pointer_type_tokens": v["raw_pointer_types_removed"]} for k, v in self.selected[ds.FIELD].items()}
        inventory = dict(binary_sha256=sha, dsfield_deltas=measured)
        def check(result):
            verify_release(preview, self.selected, inventory, result, ds.FIELD, "dsfield_deltas")
        check(observed)
        for changes in ({"elf_sha256": "0" * 64}, {"dsfield_public_comparisons": 0}, {"dsfield_profiles": []}):
            with self.assertRaises(ValueError):
                check(dict(observed, **changes))
        measured[self.key]["raw_pointer_type_tokens"] -= 1
        with self.assertRaises(ValueError):
            check(observed)

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
