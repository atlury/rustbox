#!/usr/bin/env python3
"""Exercise saved-build selection, package retries and preservation of earlier release logs."""
# SPDX-License-Identifier: 0BSD
from hashlib import sha256
import json
from pathlib import Path
from shutil import copyfile
import subprocess
from tempfile import TemporaryDirectory
import unittest

RUNNER = Path(__file__).resolve().parents[1] / "scripts/qualify_pointer_release.sh"


class Resume(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        scripts = self.root / "scripts"
        scripts.mkdir()
        self.runner = scripts / RUNNER.name
        copyfile(RUNNER, self.runner)
        self.out = self.root / "build"
        self.first = self.out / "verified"
        self.independent = self.first / "independent/results.json"
        self.independent.parent.mkdir(parents=True)
        self.independent.write_text('{"statuses":{"gzip":0}}')
        self.parent = self.root / "parent.json"
        self.parent.write_text("{}")
        self.data = b"saved executable"
        self.binary = self.out / "rustbox"
        self.binary.write_bytes(self.data)
        self.link = dict(binary=dict(sha256=sha256(self.data).hexdigest()), lz4_benchmark_dictionary={"enabled":1})
        live = self.root / "work/analysis/rustbox-multicall-link.json"
        live.parent.mkdir(parents=True)
        for path in (live, self.first / "release.json", self.out / "release.json"):
            path.write_text(json.dumps(self.link))
        (self.first / "control.json").write_bytes(self.parent.read_bytes())
        # A successful fixture invocation captures the exact downstream arguments.
        (scripts / "verify_dirhash_release.py").write_text(
            'import json,sys\nfrom pathlib import Path\nout=Path(sys.argv[3]);out.mkdir()\n'
            '(out/"arguments.json").write_text(json.dumps(sys.argv[1:]))\n')
        for name in ("rank_foreign_declarations", "rank_fixed_array_helpers", "rank_shared_applet_modules", "record_pointer_release"):
            (scripts / (name + ".py")).write_text("print('{}')\n")

    def invoke(self, option="--lz4-benchmark-dictionary"):
        return subprocess.run(["sh", self.runner, "--resume-built", option, self.parent, self.out], capture_output=True)

    def test_retries_in_new_directory_and_preserves_package_results(self):
        for expected in (True, False):
            if not expected:
                self.independent.write_text('{"statuses":{"gzip":1}}')
            previous = set(self.out.glob("retry.*"))
            result = self.invoke()
            self.assertEqual(result.returncode, 0, result.stderr)
            folder, = set(self.out.glob("retry.*")) - previous
            args = json.loads((folder / "verified/arguments.json").read_bytes())
            self.assertEqual("--independent-replay" in args, expected)
            self.assertEqual(Path(args[1]), self.binary)
            self.assertTrue(self.independent.exists())

    def test_saved_parent_before_first_verifier_run(self):
        (self.out / "parent.json").write_bytes(self.parent.read_bytes())
        (self.first / "release.json").unlink()
        (self.first / "control.json").unlink()
        self.independent.unlink()
        self.assertEqual(self.invoke().returncode, 0)

    def test_wrong_substitution_binary_and_control_are_rejected(self):
        self.assertNotEqual(self.invoke("--curl-manual").returncode, 0)
        self.binary.write_bytes(b"other")
        self.assertNotEqual(self.invoke().returncode, 0)
        self.binary.write_bytes(self.data)
        self.parent.write_text('{"different":true}')
        self.assertNotEqual(self.invoke().returncode, 0)
        self.assertFalse(list(self.out.glob("retry.*")))


if __name__ == "__main__":
    unittest.main()
