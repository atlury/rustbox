#!/usr/bin/env python3
"""Enroll and install byte-identical archives built with shared stdio layouts."""
# SPDX-License-Identifier: GPL-3.0-or-later
from functools import partial

import prepare_identical_archives as archives

enroll = partial(archives.enroll, layer="shared_stdio_layouts")
prepare = partial(archives.prepare, layer="shared_stdio_layouts")
validate_link = partial(archives.validate_link, layer="shared_stdio_layouts")

if __name__ == "__main__":
    archives.main("shared_stdio_layouts")
