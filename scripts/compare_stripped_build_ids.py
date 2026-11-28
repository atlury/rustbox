#!/usr/bin/env python3
"""Compare both entire GNU-stripped executables, allowing only the GNU build ID descriptor to differ."""
# SPDX-License-Identifier: 0BSD
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import struct
import subprocess
from tempfile import TemporaryDirectory

from check_cargo_private_inlines import digest

NOTE = re.compile(r"^\s*\[\s*\d+\]\s+\.note\.gnu\.build-id\s+NOTE\s+[\da-fA-F]+\s+([\da-fA-F]+)\s+([\da-fA-F]+)\s", re.M)


def snapshot(elf, stripped, receipt):
    if digest(elf) != receipt["sha256"]:
        raise ValueError("input ELF differs from the recorded link")
    subprocess.run(["strip", "--strip-all", "-o", stripped, elf], check=True)
    data = stripped.read_bytes()
    checksum = sha256(data).hexdigest()
    if checksum != receipt["stripped_sha256"] or len(data) != receipt["stripped_bytes"]:
        raise ValueError("GNU strip did not reproduce the recorded image")
    sections = subprocess.check_output(["readelf", "--wide", "--sections", stripped], text=True)
    matches = NOTE.findall(sections)
    if len(matches) != 1 or data[:6] != b"\x7fELF\x02\x01":
        raise ValueError("expected one GNU build ID section in a little-endian ELF64 image")
    offset, size = (int(n, 16) for n in matches[0])
    if size < 17 or offset + size > len(data):
        raise ValueError("invalid ELF note bounds")
    namesz, descsz, kind = struct.unpack_from("<III", data, offset)
    if (namesz != 4 or kind != 3 or data[offset + 12:offset + 16] != b"GNU\0"
            or descsz == 0 or 16 + ((descsz + 3) // 4) * 4 != size):
        raise ValueError("expected exactly one GNU build ID note")
    start = offset + 16
    end = start + descsz
    outside = sha256(data[:start])
    outside.update(data[end:])
    return data, start, end, dict(stripped_sha256=checksum, build_id=data[start:end].hex(),
                                  outside_descriptor_sha256=outside.hexdigest())


def compare(parent, candidate, comparison):
    raw = comparison.read_bytes()
    receipts = json.loads(raw)
    with TemporaryDirectory() as tmp:
        original, start, end, before = snapshot(parent, Path(tmp) / "parent", receipts["parent"])
        result, other_start, other_end, after = snapshot(candidate, Path(tmp) / "candidate", receipts["candidate"])
    if (len(original), start, end) != (len(result), other_start, other_end):
        raise ValueError("ELF lengths or GNU build ID locations differ")
    if original[:start] != result[:start] or original[end:] != result[end:]:
        raise ValueError("stripped executable differs outside its GNU build ID descriptor")
    return dict(link_comparison_sha256=sha256(raw).hexdigest(), parent=before, candidate=after,
                stripped_bytes=len(original), descriptor_offset=start, descriptor_bytes=end-start,
                differing_bytes=sum(a != b for a, b in zip(original[start:end], result[start:end])))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("parent", "candidate", "comparison"):
        parser.add_argument(field, type=Path)
    args = parser.parse_args()
    print(json.dumps(compare(args.parent, args.candidate, args.comparison), indent=2, sort_keys=True))
