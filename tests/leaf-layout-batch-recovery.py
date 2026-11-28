#!/usr/bin/env python3
"""Check accounting and stale-input rejection for mixed layout recovery batches."""
# SPDX-License-Identifier: 0BSD
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import recover_leaf_layout_batch as batch


def write(path, value):
    path.write_text(json.dumps(value))


class Recovery(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.link, self.rank, self.output = (root / n for n in ("link", "rank", "result"))
        write(self.link, dict(binary=dict(sha256="elf"), source_library_sha256={k: "control" for k in ("a", "b", "c")}))
        write(self.rank, {})
        self.sources = [root / name for name in ("cargo", "direct")]
        for folder, rows in zip(self.sources, [[("a", True, ["A"]), ("b", False, ["B"])], [("c", False, ["C", "D"])]]):
            folder.mkdir()
            (folder / "batch.lock").touch()
            summary = dict(link_sha256=batch.digest(self.link), ranking_sha256=batch.digest(self.rank), identical={},
                           changed={}, errors={}, selected=len(rows), verified_pointer_types_removed=0)
            for key, same, names in rows:
                dest = batch.archive_folder(folder, key)
                dest.mkdir()
                archive = "control" if same else "different"
                count = 3 * len(names)
                write(dest / "pilot.json", dict(archive=key, control_binary_sha256="elf", control_sha256="control",
                                                candidate_sha256=archive, raw_pointer_types_removed=count, leaf_layouts=dict.fromkeys(names)))
                summary["identical" if same else "changed"][key] = dict(pilot_sha256=batch.digest(dest / "pilot.json"),
                       archive_sha256=archive, raw_pointer_types_removed=count, layouts=names)
                if same:
                    summary["verified_pointer_types_removed"] += count
            write(folder / "results.json", summary)

    def run_batch(self):
        return batch.run(self.link, self.rank, self.sources, self.output, 4)

    def test_recount_and_resume(self):
        def subset(link, rank, folder, dest, limit):
            dest.mkdir(exist_ok=True)
            result = dict(raw_pointer_types_removed=3, accepted=["C"], whole_receipt_sha256=batch.digest(folder / "pilot.json"))
            write(dest / "results.json", result)
            return result
        with patch.object(batch, "recover", side_effect=subset):
            first = self.run_batch()
            self.assertEqual(first, self.run_batch())
        self.assertEqual(first["primary_pointer_types_removed"], 3)
        self.assertEqual(first["recovered_pointer_types_removed"], 3)
        self.assertEqual(first["skipped_single_layouts"], ["b"])
        self.assertEqual(list(first["additional"]), ["c"])

    def test_rejects_overlap(self):
        self.sources.append(self.sources[0])
        with self.assertRaisesRegex(ValueError, "overlap"):
            self.run_batch()

    def test_rejects_stale_ranking(self):
        write(self.rank, ["new"])
        with self.assertRaisesRegex(ValueError, "different release"):
            self.run_batch()

    def test_rejects_false_classification(self):
        path = self.sources[0] / "results.json"
        data = json.loads(path.read_bytes())
        data["changed"]["a"] = data["identical"].pop("a")
        data["verified_pointer_types_removed"] = 0
        write(path, data)
        with self.assertRaisesRegex(ValueError, "disagree"):
            self.run_batch()

    def test_rejects_replacing_source(self):
        self.output = self.sources[0]
        with self.assertRaisesRegex(ValueError, "separate output"):
            self.run_batch()


if __name__ == "__main__":
    unittest.main()
