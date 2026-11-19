#!/usr/bin/env python3
"""Regression checks for translation-slice completeness guards."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ExtractCompdbTests(unittest.TestCase):
    def test_repeated_source_configurations_are_rejected_for_c2rust(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "compile_commands.json"
            output = root / "slice.json"
            database.write_text(
                json.dumps([
                    {"file": "/src/shared.c", "output": "src/libsinglebin_a_a.o", "arguments": ["cc", "-DA"]},
                    {"file": "/src/shared.c", "output": "src/libsinglebin_b_b.o", "arguments": ["cc", "-DB"]},
                ]),
                encoding="utf-8",
            )
            process = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/extract_compdb_slice.py"),
                    "--database", str(database),
                    "--output", str(output),
                    "--output-regex", "libsinglebin_",
                    "--expected-commands", "2",
                    "--require-unique-sources",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertNotEqual(process.returncode, 0)
            self.assertIn("silently deduplicate", process.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
