"""Preserve byte positions in source ranges already validated by the private-inline replayer."""
# SPDX-License-Identifier: 0BSD

WHITESPACE = bytes(c if c in b" \t\r\n" else 32 for c in range(256))


def pad_removed_items(crate, ranges, originals):
    for name, spans in ranges.items():
        data = bytearray(originals[name])
        for start, end in spans:
            data[start:end] = data[start:end].translate(WHITESPACE)
        (crate / name).write_bytes(data)
