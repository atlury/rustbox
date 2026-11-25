#!/usr/bin/env python3
"""Materialize Bison's checked constant lengths from its original compiler inputs."""
# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path

from build_literal_lengths_pilot import MARKER
from cargo_archive_pilot import stage_selected_archive
from check_cargo_private_inlines import ROOT
from qualified_cargo_archive import QualifiedArchive

KEY = "work/analysis/bison-3.8.2/translations/c2rust-0.22.1/bison-3.8.2-stable/target/release/libbison_3_8_2_normalized_audit.a"
selection = QualifiedArchive(KEY, "bison_literal_lengths", "literal-lengths", ROOT / "batches/bison-literal-lengths.json",
                             ROOT / "evidence/bison-literal-length-pilot.json")


def build(parent: Path, output: Path):
    stage_selected_archive(parent, output, KEY, MARKER, "build_literal_lengths_pilot.py")


if __name__ == "__main__":
    selection.prepare(selection.pinned(), build)
