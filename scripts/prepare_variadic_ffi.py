#!/usr/bin/env python3
"""Enroll shared variadic C declarations after byte-identical cold builds."""
# SPDX-License-Identifier: GPL-3.0-or-later
from prepare_identical_archives import main

if __name__ == "__main__":
    main("shared_variadic_ffi")
