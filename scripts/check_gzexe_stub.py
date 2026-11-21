#!/usr/bin/env python3
"""Verify Rustbox's embedded gzexe launcher against a canonical gzexe."""

from __future__ import annotations

import argparse
import ast
import difflib
import os
import re
import subprocess
import tempfile
from pathlib import Path


def embedded_stub(source: Path) -> bytes:
    text = source.read_text(encoding="utf-8")
    begin = text.index("static char const gzexe_stub[] =")
    end = text.index(";\n\nstatic int\ngzexe_help", begin)
    literals = re.findall(r'"(?:[^"\\]|\\.)*"', text[begin:end])
    return "".join(ast.literal_eval(item) for item in literals).encode()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--canonical-gzexe", type=Path, required=True)
    args = parser.parse_args()
    ours = embedded_stub(args.source)
    with tempfile.TemporaryDirectory(prefix="rustbox-gzexe-stub-") as temporary:
        tool = Path(temporary) / "tool"
        tool.write_bytes(b"#!/bin/sh\nprintf 'payload\\n'\n")
        tool.chmod(0o755)
        subprocess.run(
            [str(args.canonical_gzexe), str(tool)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        )
        wrapped = tool.read_bytes()
    boundary = wrapped.index(b"\x1f\x8b")
    canonical = wrapped[:boundary]
    if ours != canonical:
        print("".join(difflib.unified_diff(
            canonical.decode().splitlines(keepends=True),
            ours.decode().splitlines(keepends=True),
            fromfile="canonical", tofile="embedded",
        )), end="")
        return 1
    print(f"gzexe launcher: {len(ours)} bytes match canonical")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
