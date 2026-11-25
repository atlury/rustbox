#!/usr/bin/env python3
"""Enroll and install byte-identical archives built with compiler-checked Rust C strings."""
# SPDX-License-Identifier: GPL-3.0-or-later
from prepare_identical_archives import main

if __name__ == "__main__":
    main("native_c_strings")
