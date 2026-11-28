#!/usr/bin/env python3
"""Keep direct-rustc subset module paths when mode switches and positional arguments interleave."""
# SPDX-License-Identifier: 0BSD
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_staged_c_strings as staged


class CompilerArguments(unittest.TestCase):
    def test_subset(self):
        paths = ["src/bridge/fdb.rs", "src/lib/color.rs"]
        base = ["parent.json", "result", "libbridge.a"]
        for args in (["--closed-inlines", *base, *paths], [*base, "--closed-inlines", *paths],
                     [*base, paths[0], "--closed-inlines", paths[1]], [*base, *paths, "--closed-inlines"]):
            with self.subTest(args=args), patch.object(staged, "compile_archive") as compile_archive:
                staged.main(args)
                self.assertEqual(compile_archive.call_args.args, (Path(base[0]), Path(base[1]), base[2], paths))
                self.assertTrue(compile_archive.call_args.kwargs["closed_inlines"])

    def test_whole_archive(self):
        with patch.object(staged, "compile_archive") as compile_archive:
            staged.main(["parent.json", "result", "libbridge.a", "--all-scalar-ffi"])
            self.assertIsNone(compile_archive.call_args.args[3])
            self.assertEqual(compile_archive.call_args.kwargs["scalar_ffi"], "all")


if __name__ == "__main__":
    unittest.main()
