#!/usr/bin/env python3
"""Find parsed, byte-preserving Rust C-string conversions across compiler-selected multicall inputs."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from audit_linked_pointers import measure
from check_cargo_private_inlines import ROOT


def rank(link, tool):
    raw = link.read_bytes()
    uses = defaultdict(Counter)
    with TemporaryDirectory() as temp:
        scratch = Path(temp)
        def collect(archive, module, digest, data):
            if b"c_char" not in data or b"*const u8" not in data or b'\\0"' not in data:
                return
            name = digest.hex() + ".rs"
            if name not in uses:
                (scratch / name).write_bytes(data)
            uses[name][str(archive)] += 1
        inventory = measure(json.loads(raw), inspect_module=collect)
        parsed = subprocess.check_output([tool, scratch], input=json.dumps(sorted(uses)).encode())
    counts = Counter()
    unique = 0
    for name, edits in json.loads(parsed).items():
        unique += len(edits)
        for archive, copies in uses[name].items():
            counts[archive] += len(edits) * copies
    if raw != link.read_bytes():
        raise ValueError("release changed during the scan")
    return dict(binary_sha256=inventory["binary_sha256"], link_report_sha256=sha256(raw).hexdigest(),
                syntax_source_sha256=sha256((ROOT / "tools/private-inlines/src/bin/c-string-literals.rs").read_bytes()).hexdigest(),
                unique_source_conversions=unique, compiler_input_conversions=sum(counts.values()),
                archives=dict(sorted(counts.items())))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path)
    args = parser.parse_args()
    target = ROOT / "work/analysis/syntax-tools-native"
    subprocess.run(["cargo", "build", "--locked", "--offline", "--release", "--manifest-path",
                    ROOT / "tools/private-inlines/Cargo.toml", "--bin", "c-string-literals", "--target-dir", target], check=True)
    print(json.dumps(rank(args.link, target / "release/c-string-literals"), indent=2, sort_keys=True))
