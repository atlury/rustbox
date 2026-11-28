#!/usr/bin/env python3
"""Rank repeated private C ABI functions with signatures expressible entirely in scalar and pointer types."""
# SPDX-License-Identifier: 0BSD
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from audit_linked_pointers import measure
from check_cargo_private_inlines import ROOT, digest
from verify_c_string_sources import syntax_tool


def rank(link, *, variadic=False):
    raw = link.read_bytes()
    copies = defaultdict(Counter)
    by_signature = defaultdict(Counter)
    tool = syntax_tool("variadic-ffi" if variadic else "scalar-ffi")
    with TemporaryDirectory() as tmp:
        directory = Path(tmp)
        def capture(archive, module, checksum, data):
            if b'extern "C"' not in data or (variadic and b"..." not in data):
                return
            name = checksum.hex() + ".rs"
            if name not in copies:
                (directory / name).write_bytes(data)
            copies[name][str(archive)] += 1
        measure(json.loads(raw), inspect_module=capture)
        scanned = json.loads(subprocess.check_output([tool, directory], input=json.dumps(sorted(copies)).encode()))
        for name, rows in scanned.items():
            symbols = Counter(row[0].split("(")[0] for row in rows)
            for signature, *_ in rows:
                if symbols[signature.split("(")[0]] == 1:
                    by_signature[signature].update(copies[name])
    totals = Counter()
    groups = []
    for signature, counts in by_signature.items():
        pointers = signature.count("*")
        repeated = {key: (n-1)*pointers for key, n in counts.items() if n > 1}
        if repeated:
            totals.update(repeated)
            groups.append(dict(signature=signature, pointer_types=sum(repeated.values()), archives=repeated))
    groups.sort(key=lambda g: (-g["pointer_types"], g["signature"]))
    if raw != link.read_bytes():
        raise ValueError("release changed during FFI inventory")
    result = dict(link_sha256=sha256(raw).hexdigest(), binary_sha256=json.loads(raw)["binary"]["sha256"],
                scanner_source_sha256=digest(ROOT/"tools/private-inlines/src/bin/scalar-ffi.rs"),
                candidate_pointer_types=sum(totals.values()), archives=dict(totals), signatures=groups)
    if variadic:
        result["variadic_scanner_sha256"] = digest(ROOT / "tools/private-inlines/src/bin/variadic-ffi.rs")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path)
    parser.add_argument("--variadic", action="store_true", help="rank C variadic declarations with matching fixed parameter types")
    args = parser.parse_args()
    print(json.dumps(rank(args.link, variadic=args.variadic), indent=2, sort_keys=True))
