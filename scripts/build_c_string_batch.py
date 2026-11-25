#!/usr/bin/env python3
"""Cold-build ranked C-string candidates and retain only archives that reproduce all original bytes."""
# SPDX-License-Identifier: GPL-3.0-or-later
from build_shared_stdio_batch import main

if __name__ == "__main__":
    main(__doc__, c_strings=True)
