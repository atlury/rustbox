#!/usr/bin/env python3
"""Qualify the three packed E2fsprogs error-name archives together in the complete Linux ELF."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import json
from pathlib import Path
import subprocess
import sys

from check_cargo_private_inlines import ROOT, digest
from link_rustbox_multicall import E2FSPROGS_PROGRAMS, coalesce_identical_archive_members, namespace_e2fsprogs_programs
from preview_cargo_multicall import preview_link

PACKAGE = ROOT / "tests/e2fsprogs-error-names"
BUILD = Path("/rustbox-coreutils/canonical-clang-no-security-compdb")


def preview(parent, log, batch, output):
    batch = batch.resolve()
    raw = parent.read_bytes()
    release = json.loads(raw)
    receipt = ROOT / "evidence/e2fsprogs-packed-error-names-archives.json"
    proof = json.loads(receipt.read_bytes())
    selected = proof["api"]["archive_checks"]
    if (set(selected) != {"debugfs", "dumpe2fs", "tune2fs"} or proof["parent_link_report_sha256"] != digest(parent)
            or proof["public"]["elf_sha256"] != release["binary"]["sha256"]):
        raise ValueError("expected all three qualified archives on the selected parent")
    inputs = release["source_library_sha256"]
    runtime, = [ROOT / key for key in inputs if Path(key).name == "libprocps_ng_4_0_7_normalized_audit.a"]
    if digest(runtime) != inputs[str(runtime.relative_to(ROOT))]:
        raise ValueError("unexpected shared Rust runtime archive")

    def prepare(which, stage):
        libraries = {}
        hashes = {}
        for engine in E2FSPROGS_PROGRAMS:
            archive_name = "lib" + engine + "_audit.a"
            if engine not in selected:
                libraries[engine] = BUILD / "src/.rustbox-e2fsprogs-runtime" / engine / archive_name
                continue
            row = selected[engine]
            key = row["archive"]
            folder = batch / engine
            if (json.loads((folder / "pilot.json").read_bytes()) != row or Path(key).name != archive_name
                    or inputs[key] != row["control_sha256"]):
                raise ValueError("incomplete error-name qualification for " + engine)
            archive = ROOT / key if which == "parent" else folder / archive_name
            hashes[engine] = digest(archive)
            if hashes[engine] != row["control_sha256" if which == "parent" else "candidate_sha256"]:
                raise ValueError("unexpected linker input for " + engine)
            built, members, _ = coalesce_identical_archive_members(runtime, archive, stage / "coalesced" / engine, engine)
            if members != release["e2fsprogs_coalesced_runtime_members"][engine]:
                raise ValueError("different Rust runtime selection for " + engine)
            libraries[engine] = built
        mapped, symbols = namespace_e2fsprogs_programs(libraries, stage)
        if symbols != release["e2fsprogs_namespaced_symbols"]:
            raise ValueError("E2fsprogs C symbol isolation differs")
        return list(mapped.values()), {mapped[engine] for engine in selected}, dict(engine_sha256=hashes)

    def exercise(elf, stage):
        public = json.loads(subprocess.check_output([sys.executable, "-B", PACKAGE / "images.py", elf]))
        if any(public[k] != v for k, v in proof["public_baseline"].items() if k != "elf_sha256"):
            raise ValueError("full executable differs from the canonical ext2 image comparisons")
        driver = ROOT / "tests/e2fsprogs-multicall-differential.py"
        comparisons = {}
        for cc in ("gcc", "clang-18"):
            report = stage / (cc + ".json")
            subprocess.run([sys.executable, "-B", driver, "--canonical-root", "/rustbox-e2fsprogs/stage-" + cc,
                            "--rustbox", elf, "--output", report], check=True)
            result = json.loads(report.read_bytes())
            if result["cases"] != result["passed"] or result["native_names"] < len(selected):
                raise ValueError("incomplete E2fsprogs multicall comparisons")
            comparisons[cc] = {k:v for k,v in result.items() if k != "records"}
        return dict(ext2_images=public, public_commands=comparisons, archive_evidence_sha256=digest(receipt))

    preview_link(parent, raw, log, output, prepare, exercise)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("parent", "log", "batch", "output"):
        p.add_argument(arg, type=Path)
    a = p.parse_args()
    preview(a.parent, a.log, a.batch, a.output)
