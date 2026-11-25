#!/usr/bin/env python3
"""Count identical verified glibc FILE definitions that can share a provider inside one Rust crate."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path

from audit_linked_pointers import measure
from share_stdio_layout import eligible


def rank(link_path):
    raw = link_path.read_bytes()
    matches = {}
    modules = defaultdict(list)

    def collect(archive, module, digest, data):
        if digest not in matches:
            matches[digest] = eligible(data)
        if matches[digest]:
            modules[str(archive)].append(str(module))

    inv = measure(json.loads(raw), inspect_module=collect)
    rows = [dict(archive=archive, modules=len(files), repeated_pointer_fields=18 * (len(files) - 1))
            for archive, files in modules.items() if len(files) > 1]
    rows.sort(key=lambda r: (-r["repeated_pointer_fields"], r["archive"]))
    if link_path.read_bytes() != raw:
        raise ValueError("link report changed during the layout scan")
    return dict(binary_sha256=inv["binary_sha256"], link_report_sha256=sha256(raw).hexdigest(),
                archives=rows, repeated_pointer_fields=sum(row["repeated_pointer_fields"] for row in rows))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path)
    print(json.dumps(rank(parser.parse_args().link), indent=2, sort_keys=True))
