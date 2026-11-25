#!/usr/bin/env python3
"""Replace double-cast NUL-terminated byte literals with compiler-checked Rust C strings."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import json
from pathlib import Path
import subprocess

from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import ROOT, LINK_REPORT, digest
from prune_private_inlines import POINTER

MARKER = ".rustbox-c-string-pilot"


def rewrite(crate, sources, tool):
    output = subprocess.check_output([tool, crate], input=json.dumps(sorted(sources)).encode())
    spans = json.loads(output)
    replacements = {}
    counts = {}
    for name, edits in spans.items():
        if name not in sources:
            raise ValueError("unselected Rust module in syntax output")
        source = (crate / name).read_bytes()
        pieces = []
        position = 0
        for start, end, spelling in edits:
            if not position <= start < end <= len(source) or not spelling.startswith('c"') or not spelling.endswith(".as_ptr()"):
                raise ValueError("unexpected C literal edit")
            pieces.extend((source[position:start], spelling.encode()))
            position = end
        result = b"".join([*pieces, source[position:]])
        if (source.count(b"\n") != result.count(b"\n")
                or len(POINTER.findall(source)) - len(POINTER.findall(result)) != 2 * len(edits)):
            raise ValueError("literal substitutions changed line counts or unexpected pointer casts")
        replacements[name] = result
        counts[name] = len(edits)
    total = sum(counts.values())
    return replacements, dict(c_string_literals=total, modules=counts, raw_pointer_types_removed=2 * total,
                              raw_ffi_pointer_extractions=total, syntax_tool_sha256=digest(tool))


def substitute(crate, sources):
    tool = ROOT / "work/analysis/private-inlines-linux/release/c-string-literals"
    return rewrite(crate, sources, tool)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--link", type=Path, default=LINK_REPORT)
    parser.add_argument("--archive", type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--output", type=Path)
    group.add_argument("--mounted", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.mounted:
        compile_mounted_sources(args.mounted, substitute, MARKER, allow_identical=True)
    else:
        if not args.archive:
            parser.error("--output requires --archive")
        stage_selected_archive(args.link, args.output.resolve(), str(args.archive), MARKER, Path(__file__).name)
