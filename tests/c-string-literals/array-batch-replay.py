#!/usr/bin/env python3
"""Replay a real static-array selection and challenge its archive, classification and count."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from recover_static_array_batch import run


def rejects(action, reason):
    try:
        action()
    except ValueError as error:
        if reason not in str(error):
            raise
    else:
        raise AssertionError(f"expected rejection for {reason}")


def test(link, whole, candidates, report):
    expected = json.loads(report.read_bytes())
    key, = expected["identical"]
    package = Path(key).parts[2]
    name = Path(key).stem + "-" + sha256(key.encode()).hexdigest()[:12]
    with TemporaryDirectory() as tmp, patch("recover_literal_array_modules.build", side_effect=AssertionError("unexpected build")):
        scratch = Path(tmp)
        selection = scratch / "candidates"
        receipt = scratch / "report.json"
        receipt.write_bytes(report.read_bytes())
        def replay():
            run(link, whole, selection, [package], check=receipt)
        rejects(replay, "missing saved archive")
        assert not selection.exists()

        archive = selection / name
        archive.mkdir(parents=True)
        for leaf in ("pilot.json", Path(key).name):
            (archive / leaf).symlink_to((candidates / name / leaf).resolve())
        comparison = archive / "comparison.json"
        comparison.write_bytes((candidates / name / comparison.name).read_bytes())
        initial = {path: path.stat().st_mtime_ns for path in scratch.rglob("*")}
        replay()
        assert initial == {path: path.stat().st_mtime_ns for path in scratch.rglob("*")}

        counted = deepcopy(expected)
        counted["verified_raw_pointer_types_removed"] += 1
        misplaced = deepcopy(expected)
        misplaced["changed"][key] = misplaced["identical"].pop(key)
        for altered in (counted, misplaced):
            receipt.write_text(json.dumps(altered))
            rejects(replay, "published array batch differs")
        receipt.write_bytes(report.read_bytes())
        altered = json.loads(comparison.read_bytes())
        altered["byte_identical"] = False
        comparison.write_text(json.dumps(altered))
        rejects(replay, "saved archive comparison differs")
    print("Replayed unchanged receipts and rejected four missing or altered inputs.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("link", "whole", "candidates", "report"):
        parser.add_argument(arg, type=Path)
    args = parser.parse_args()
    test(args.link, args.whole, args.candidates, args.report)
