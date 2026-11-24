#!/usr/bin/env python3
"""Embed E2fsprogs' canonical awk/sed generator templates as C bytes."""

from __future__ import annotations

import argparse
from pathlib import Path


TEMPLATES = {
    "rustbox_e2fs_et_h_awk": "lib/et/et_h.awk",
    "rustbox_e2fs_et_c_awk": "lib/et/et_c.awk",
    "rustbox_e2fs_ct_c_sed": "lib/ss/ct_c.sed",
    "rustbox_e2fs_ct_c_awk": "lib/ss/ct_c.awk",
}


def bytes_literal(data: bytes) -> str:
    rows = []
    for offset in range(0, len(data), 16):
        rows.append("    " + ", ".join(f"0x{byte:02x}" for byte in data[offset:offset + 16]))
    return ",\n".join(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    parts = [
        "/* Generated from signed E2fsprogs 1.47.4 templates. */",
        "#include <stddef.h>",
        "",
    ]
    for symbol, relative in TEMPLATES.items():
        data = (args.source / relative).read_bytes()
        parts.extend([
            f"const unsigned char {symbol}[] = {{",
            bytes_literal(data),
            "};",
            f"const size_t {symbol}_len = sizeof {symbol};",
            "",
        ])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(parts), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
