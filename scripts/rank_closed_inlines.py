#!/usr/bin/env python3
"""Rank groups of private inline helpers with no incoming identifier references in a leaf module."""
# SPDX-License-Identifier: 0BSD
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from audit_linked_pointers import measure
from check_cargo_private_inlines import ROOT
from prune_private_inlines import POINTER


def rank(link):
    raw = link.read_bytes()
    scanner = "closed-inlines"
    target = ROOT / "work/analysis/syntax-tools-native"
    subprocess.run(["cargo","build","--locked","--offline","--release","--manifest-path",ROOT/"tools/private-inlines/Cargo.toml",
                    "--target-dir",target,"--bin",scanner],check=True)
    copies = defaultdict(Counter)
    by_archive = defaultdict(Counter)
    with TemporaryDirectory() as tmp:
        path = Path(tmp)
        def inspect(archive, module, checksum, data):
            if b"#[inline]" not in data:
                return
            name = checksum.hex() + ".rs"
            if name not in copies:
                (path / name).write_bytes(data)
            copies[name][str(archive)] += 1
        measure(json.loads(raw), inspect_module=inspect)
        result = subprocess.check_output([target/"release"/scanner,path], input=json.dumps(dict.fromkeys(copies)).encode())
        unique = Counter()
        for name, helpers in json.loads(result).items():
            data = (path / name).read_bytes()
            totals = Counter(files=1)
            for (start, end), referenced in helpers.values():
                pointers = len(POINTER.findall(data[start:end]))
                totals.update(helpers=1, pointer_types=pointers)
                if referenced:
                    totals.update(referenced_helpers=1, referenced_pointer_types=pointers)
            if totals["pointer_types"]:
                unique.update(totals)
                for archive, count in copies[name].items():
                    by_archive[archive].update({k:v*count for k,v in totals.items()})
    if link.read_bytes() != raw:
        raise ValueError("release changed during candidate ranking")
    return dict(link_sha256=sha256(raw).hexdigest(), binary_sha256=json.loads(raw)["binary"]["sha256"],
                unique_candidates=dict(unique), compiler_input_candidates=dict(sum(by_archive.values(),Counter())),
                archives=dict(sorted(by_archive.items(),key=lambda pair:(-pair[1]["pointer_types"],pair[0]))))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("link",type=Path)
    args = p.parse_args()
    print(json.dumps(rank(args.link),indent=2))
