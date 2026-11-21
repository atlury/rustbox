#!/usr/bin/env python3
"""Exact GCC/Clang behavior comparisons for canonical GNU Grep."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Case:
    name: str
    arguments: tuple[str, ...]
    status: int
    stdin: bytes = b""
    files: tuple[tuple[str, bytes], ...] = ()


TEXT = b"alpha\nbeta\nALPHA\ngamma delta\na.c\na*c\n"


def cases() -> list[Case]:
    one = (("input", TEXT),)
    return [
        Case("help", ("--help",), 0),
        Case("version", ("--version",), 0),
        Case("bad-option", ("--definitely-invalid",), 2),
        Case("basic-match", ("alpha", "input"), 0, files=one),
        Case("basic-no-match", ("absent", "input"), 1, files=one),
        Case("stdin", ("beta",), 0, stdin=TEXT),
        Case("ignore-case", ("-i", "alpha", "input"), 0, files=one),
        Case("invert", ("-v", "alpha", "input"), 0, files=one),
        Case("line-number", ("-n", "alpha", "input"), 0, files=one),
        Case("byte-offset", ("-b", "beta", "input"), 0, files=one),
        Case("count", ("-c", "a", "input"), 0, files=one),
        Case("files-with-matches", ("-l", "beta", "input"), 0, files=one),
        Case("files-without-match", ("-L", "absent", "input"), 1, files=one),
        Case("quiet-match", ("-q", "beta", "input"), 0, files=one),
        Case("quiet-no-match", ("-q", "absent", "input"), 1, files=one),
        Case("only-matching", ("-o", "a[a-z]*", "input"), 0, files=one),
        Case("whole-line", ("-x", "beta", "input"), 0, files=one),
        Case("whole-word", ("-w", "delta", "input"), 0, files=one),
        Case("fixed-string", ("-F", "a*c", "input"), 0, files=one),
        Case("extended", ("-E", "alpha|beta", "input"), 0, files=one),
        Case("perl", ("-P", "(?<=gamma )delta", "input"), 0, files=one),
        Case("null-pattern", ("-e", "", "input"), 0, files=one),
        Case("pattern-file", ("-f", "patterns", "input"), 0,
             files=(("patterns", b"beta\ngamma\n"), ("input", TEXT))),
        Case("max-count", ("-m", "1", "a", "input"), 0, files=one),
        Case("before-context", ("-B", "1", "beta", "input"), 0, files=one),
        Case("after-context", ("-A", "1", "beta", "input"), 0, files=one),
        Case("context", ("-C", "1", "beta", "input"), 0, files=one),
        Case("binary", ("-a", "beta", "binary"), 0,
             files=(("binary", b"alpha\x00beta\n"),)),
        Case("null-data", ("-z", "beta", "records"), 0,
             files=(("records", b"alpha\x00beta\x00gamma\x00"),)),
        Case("multiple-files", ("-H", "beta", "one", "two"), 0,
             files=(("one", b"beta\n"), ("two", b"none\n"))),
        Case("no-filename", ("-h", "beta", "one", "two"), 0,
             files=(("one", b"beta\n"), ("two", b"beta\n"))),
        Case("recursive", ("-r", "needle", "tree"), 0,
             files=(("tree/a", b"needle\n"), ("tree/sub/b", b"none\n"))),
        Case("recursive-include", ("-r", "--include=*.txt", "needle", "tree"), 0,
             files=(("tree/a.txt", b"needle\n"), ("tree/b.bin", b"needle\n"))),
        Case("recursive-exclude", ("-r", "--exclude=skip", "needle", "tree"), 0,
             files=(("tree/keep", b"needle\n"), ("tree/skip", b"needle\n"))),
        Case("missing", ("needle", "missing"), 2),
        Case("suppress-missing", ("-s", "needle", "missing"), 2),
    ]


def run(binary: Path, case: Case, root: Path) -> dict[str, object]:
    (root / "grep").symlink_to(binary)
    for name, payload in case.files:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    environment = dict(os.environ)
    environment.update({"LC_ALL": "C", "TZ": "UTC", "POSIXLY_CORRECT": "1"})
    result = subprocess.run(
        ["./grep", *case.arguments], cwd=root, input=case.stdin,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment,
    )
    if result.returncode != case.status:
        raise RuntimeError(
            f"{case.name}: status {result.returncode}, expected {case.status}: "
            + result.stderr.decode(errors="replace")
        )
    return {
        "status": result.returncode,
        "stdout_bytes": len(result.stdout),
        "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
        "stderr_bytes": len(result.stderr),
        "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gcc", type=Path, required=True)
    parser.add_argument("--clang", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = []
    with tempfile.TemporaryDirectory(prefix="rustbox-grep-differential-") as temporary:
        base = Path(temporary)
        for index, case in enumerate(cases()):
            gcc_root = base / f"{index:02d}-gcc"
            clang_root = base / f"{index:02d}-clang"
            gcc_root.mkdir()
            clang_root.mkdir()
            gcc = run(args.gcc.resolve(), case, gcc_root)
            clang = run(args.clang.resolve(), case, clang_root)
            if gcc != clang:
                raise RuntimeError(f"GCC/Clang mismatch: {case.name}\n{gcc}\n{clang}")
            records.append({"index": index, "name": case.name, "exact": True, "result": gcc})
    report = {
        "schema": 1,
        "comparisons": len(records),
        "gcc_clang_exact": True,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"comparisons": len(records), "exact": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
