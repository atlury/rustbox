#!/usr/bin/env python3
"""Compare fixed-size ISO number readers in the full Linux multicall against both util-linux oracles."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from build_isosize_numbers import ARCHIVE
from check_cargo_private_inlines import ROOT, digest
from preview_cargo_multicall import preview_link


def preview(parent, log, pilot, evidence, output):
    raw = parent.read_bytes()
    release = json.loads(raw)
    tested = json.loads(evidence.read_bytes())
    row = tested["archive"]
    key = Path(ARCHIVE)
    driver = ROOT / "tests/isosize-numbers/compare.py"
    if (row != json.loads((pilot / "pilot.json").read_bytes()) or row["archive"] != ARCHIVE
            or row["control_sha256"] != release["source_library_sha256"][ARCHIVE]
            or row["control_binary_sha256"] != release["binary"]["sha256"] or tested["driver_sha256"] != digest(driver)):
        raise ValueError("archive evidence differs from the selected util-linux input")

    def prepare(which, stage):
        source = ROOT / key if which == "parent" else pilot / key.name
        checksum = row["control_sha256" if which == "parent" else "candidate_sha256"]
        if digest(source) != checksum:
            raise ValueError("unexpected util-linux archive")
        path = stage / key
        path.parent.mkdir(parents=True)
        shutil.copy2(source, path)
        return [path], {path}, dict(archive_sha256=checksum)

    def exercise(elf, stage):
        root = Path("/rustbox-util-linux")
        binaries = {cc:root / f"canonical-{cc}-compdb/isosize" for cc in ("gcc", "clang")}
        if {cc:digest(p) for cc,p in binaries.items()} != tested["canonical_binaries"]:
            raise ValueError("canonical isosize binaries differ")
        with TemporaryDirectory(dir=stage) as tmp:
            profiles = runpy.run_path(str(driver))["compare_profiles"](dict(binaries, multicall=elf), Path(tmp))
        if (profiles["profiles"] != tested["profiles"] or profiles["image_count"] != tested["image_count"]
                or profiles["memcheck_runs"] != 3):
            raise ValueError("full executable differs from the qualified archive")
        batch = {}
        # Some batch cases run as nobody. Expose only the candidate executable.
        with TemporaryDirectory() as tmp:
            public_dir = Path(tmp)
            public_elf = public_dir / "rustbox"
            shutil.copyfile(elf, public_elf)
            public_elf.chmod(0o555)
            public_dir.chmod(0o755)
            for cc, binary in binaries.items():
                report = stage / (cc + ".json")
                subprocess.run([sys.executable, "-B", ROOT / "tests/util-linux-small-02-differential.py",
                                "--canonical-directory",binary.parent,"--hybrid",public_elf,"--output",report],check=True)
                results = json.loads(report.read_bytes())
                if not results["cases"] or results["passed"] != results["cases"]:
                    raise ValueError("incomplete util-linux comparisons")
                batch[cc] = results["passed"]
        return dict(iso_numbers=profiles, batch_cases=batch, archive_evidence_sha256=digest(evidence))

    preview_link(parent, raw, log, output, prepare, exercise, direct_archives=(key,))


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("parent","log","pilot","evidence","output"):
        p.add_argument(name,type=Path)
    a=p.parse_args()
    preview(a.parent,a.log,a.pilot,a.evidence,a.output)
