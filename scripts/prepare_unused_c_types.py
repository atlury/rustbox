#!/usr/bin/env python3
"""Prepare byte-identical archives after removing unused C declarations."""
# SPDX-License-Identifier: 0BSD
from prepare_identical_archives import main

if __name__ == "__main__":
    main("unused_c_types")
