#!/usr/bin/env python3
"""Build and differentially qualify the xattr hash replacement in selected E2fsprogs archives."""
# SPDX-License-Identifier: LGPL-2.0-only
import argparse
import json
from pathlib import Path

from build_e2fsprogs_xattr_hash import build
from qualify_e2fsprogs_bitmap_bits import qualify


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("link", "inventory", "output"):
        p.add_argument(name, type=Path)
    p.add_argument("--archive", action="append", default=[], help="limit qualification to this archive basename")
    a = p.parse_args()
    result = qualify(a.link, a.inventory, a.output, set(a.archive), build_pair=build,
                     test_driver="test_e2fsprogs_xattr_hash.py", cases=280576)
    print(json.dumps(result, indent=2, sort_keys=True))
