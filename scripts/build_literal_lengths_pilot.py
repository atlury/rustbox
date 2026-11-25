#!/usr/bin/env python3
"""Replace direct libc strlen calls on verified byte literals with constant byte lengths."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import json
from pathlib import Path
import re
import subprocess

from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import ROOT, digest
from prune_private_inlines import POINTER

MARKER = ".rustbox-literal-length-pilot"


def rewrite(crate, sources, checker):
    edits = json.loads(subprocess.check_output([checker, crate], input=json.dumps(sorted(sources)).encode()))
    if not edits.keys() <= set(sources):
        raise ValueError("unselected module in length analysis")
    replacements, counts = {}, {}
    for name, spans in edits.items():
        source = (crate / name).read_bytes()
        parts = []
        offset = 0
        for start, end, replacement in spans:
            if (not offset <= start < end <= len(source) or not source[start:end].startswith(b"strlen(")
                    or not re.fullmatch(r"\([0-9]+usize[\r\n]*\)", replacement)):
                raise ValueError("unexpected length substitution")
            parts.extend((source[offset:start], replacement.encode("ascii")))
            offset = end
        candidate = b"".join([*parts, source[offset:]])
        if (candidate.count(b"\n") != source.count(b"\n")
                or len(POINTER.findall(source)) - len(POINTER.findall(candidate)) != 2 * len(spans)):
            raise ValueError("source coordinates or cast count changed unexpectedly")
        replacements[name] = candidate
        counts[name] = len(spans)
    total = sum(counts.values())
    return replacements, dict(strlen_calls_removed=total, raw_pointer_types_removed=2 * total,
                              modules=counts, syntax_tool_sha256=digest(checker))


def substitute(crate, sources):
    return rewrite(crate, sources, ROOT / "work/analysis/private-inlines-linux/release/literal-lengths")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--output", type=Path)
    group.add_argument("--mounted", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--link", type=Path)
    parser.add_argument("--archive")
    args = parser.parse_args()
    if args.mounted:
        compile_mounted_sources(args.mounted, substitute, MARKER, allow_identical=True)
    elif args.link and args.archive:
        stage_selected_archive(args.link, args.output.resolve(), args.archive, MARKER, Path(__file__).name)
    else:
        parser.error("--output requires --link and --archive")
