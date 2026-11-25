#!/usr/bin/env python3
"""Locate generated glibc classification table reads with explicit unsigned-byte indexes."""
# SPDX-License-Identifier: 0BSD
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re

from audit_linked_pointers import measure

# Match the narrow emitted spelling. This is a source ranking. Each
# substitution must separately establish the types, bindings and evaluation order.
INT = rb"::core::ffi::c_int"
BYTE = rb"::core::ffi::c_uchar"
USHORT = rb"::core::ffi::c_ushort"
FLAGS = "upper lower alpha digit xdigit space print graph blank cntrl punct alnum".split()
DECL = b"fn __ctype_b_loc() -> *mut *const ::core::ffi::c_ushort;"
ACCESS = re.compile(rb"\*\s*\(\s*\*\s*__ctype_b_loc\(\)\s*\)\s*\.offset\(\s*"
                    rb"(?P<value>\*?\s*[A-Za-z_]\w*)\s+as\s+" + BYTE + rb"\s+as\s+" + INT +
                    rb"\s+as\s+isize\s*,?\s*\)\s+as\s+" + INT + rb"\s*&\s*_IS(?P<flag>\w+)\s+as\s+" +
                    INT + rb"\s+as\s+" + USHORT + rb"\s+as\s+" + INT + rb"\b")


def matches(data):
    allowed = []
    for i, flag in enumerate(FLAGS):
        # The project targets glibc Linux/x86-64, where the flag words are stored big-endian.
        expected = int.from_bytes((1 << i).to_bytes(2, "big"), "little")
        if re.search(rb"\bconst _IS" + flag.encode() + rb":\s*\w+\s*=\s*" + str(expected).encode() + rb";", data):
            allowed.append(flag.encode())
    return [m for m in ACCESS.finditer(data) if m["flag"] in allowed]


def rank(link):
    raw = link.read_bytes()
    cache = {}
    packages = {}
    def collect(archive, module, checksum, data):
        if DECL not in data:
            return
        if checksum not in cache:
            uses = matches(data)
            cache[checksum] = (Counter(m["flag"].decode() for m in uses),
                               len(uses) > 0 and data.count(b"__ctype_b_loc") == len(uses) + 1)
        flags, complete = cache[checksum]
        if flags:
            row = packages.setdefault(str(archive), dict(modules=0, complete_spellings=0, flag_uses=Counter()))
            row["modules"] += 1
            row["complete_spellings"] += int(complete)
            row["flag_uses"].update(flags)
    measure(json.loads(raw), inspect_module=collect)
    if raw != link.read_bytes():
        raise ValueError("link selection changed during ranking")
    return dict(link_report_sha256=sha256(raw).hexdigest(), archives=packages,
                matched_uses=sum(sum(r["flag_uses"].values()) for r in packages.values()),
                matched_modules=sum(r["modules"] for r in packages.values()),
                declarations_with_every_use_matched=sum(r["complete_spellings"] for r in packages.values()))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("link", type=Path)
    print(json.dumps(rank(p.parse_args().link), indent=2, sort_keys=True))
