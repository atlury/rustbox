#!/usr/bin/env python3
"""Reconstruct the qualified timestamp archive from the release compiler inputs."""
# SPDX-License-Identifier: GPL-3.0-or-later
from build_tar_timespec_pilot import ARCHIVE, build
from check_cargo_private_inlines import ROOT
from qualified_cargo_archive import QualifiedArchive

selection = QualifiedArchive(ARCHIVE, "tar_borrowed_timestamps", "borrowed-timestamps",
                             ROOT / "batches/tar-borrowed-timestamps.json",
                             ROOT / "evidence/tar-borrowed-timespec-pilot.json")

if __name__ == "__main__":
    selection.prepare(selection.pinned(), build)
