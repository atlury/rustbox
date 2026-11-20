#!/usr/bin/env python3
"""Exact GCC/Clang behavior comparisons for canonical GNU Diffutils."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Case:
    name: str
    utility: str
    arguments: tuple[str, ...]
    expected_status: int
    stdin: bytes = b""
    files: tuple[tuple[str, bytes], ...] = ()


def cases() -> list[Case]:
    same = (("left", b"alpha\nbeta\n"), ("right", b"alpha\nbeta\n"))
    changed = (("left", b"alpha\nbeta\n"), ("right", b"alpha\nBETA\n"))
    return [
        Case("cmp-help", "cmp", ("--help",), 0),
        Case("cmp-version", "cmp", ("--version",), 0),
        Case("cmp-bad-option", "cmp", ("--definitely-invalid",), 2),
        Case("cmp-same", "cmp", ("left", "right"), 0, files=same),
        Case("cmp-different", "cmp", ("left", "right"), 1, files=changed),
        Case("cmp-verbose", "cmp", ("-l", "left", "right"), 1, files=changed),
        Case("cmp-byte-number", "cmp", ("-b", "left", "right"), 1, files=changed),
        Case("cmp-ignore-initial", "cmp", ("-i", "6", "left", "right"), 1, files=changed),
        Case("cmp-limit", "cmp", ("-n", "5", "left", "right"), 0, files=changed),
        Case("cmp-stdin", "cmp", ("-", "right"), 0, stdin=b"alpha\nbeta\n", files=(("right", b"alpha\nbeta\n"),)),
        Case("cmp-missing", "cmp", ("missing", "right"), 2, files=(("right", b"x\n"),)),

        Case("diff-help", "diff", ("--help",), 0),
        Case("diff-version", "diff", ("--version",), 0),
        Case("diff-bad-option", "diff", ("--definitely-invalid",), 2),
        Case("diff-same", "diff", ("left", "right"), 0, files=same),
        Case("diff-normal", "diff", ("left", "right"), 1, files=changed),
        Case("diff-unified", "diff", ("-u", "left", "right"), 1, files=changed),
        Case("diff-context", "diff", ("-c", "left", "right"), 1, files=changed),
        Case("diff-side-by-side", "diff", ("-y", "left", "right"), 1, files=changed),
        Case("diff-brief", "diff", ("-q", "left", "right"), 1, files=changed),
        Case("diff-ignore-case", "diff", ("-i", "left", "right"), 0, files=changed),
        Case("diff-ignore-space", "diff", ("-w", "left", "right"), 0,
             files=(("left", b"a b c\n"), ("right", b"abc\n"))),
        Case("diff-ignore-blank", "diff", ("-B", "left", "right"), 0,
             files=(("left", b"alpha\n\nbeta\n"), ("right", b"alpha\nbeta\n"))),
        Case("diff-recursive", "diff", ("-ru", "a", "b"), 1,
             files=(("a/one", b"same\n"), ("b/one", b"same\n"),
                    ("a/two", b"old\n"), ("b/two", b"new\n"))),
        Case("diff-new-file", "diff", ("-ruN", "a", "b"), 1,
             files=(("a/only-left", b"left\n"), ("b/only-right", b"right\n"))),
        Case("diff-stdin", "diff", ("-", "right"), 0, stdin=b"alpha\nbeta\n",
             files=(("right", b"alpha\nbeta\n"),)),
        Case("diff-binary", "diff", ("left", "right"), 1,
             files=(("left", b"a\x00b"), ("right", b"a\x00c"))),
        Case("diff-missing", "diff", ("missing", "right"), 2, files=(("right", b"x\n"),)),

        Case("diff3-help", "diff3", ("--help",), 0),
        Case("diff3-version", "diff3", ("--version",), 0),
        Case("diff3-bad-option", "diff3", ("--definitely-invalid",), 2),
        Case("diff3-same", "diff3", ("mine", "older", "yours"), 0,
             files=(("mine", b"a\nb\n"), ("older", b"a\nb\n"), ("yours", b"a\nb\n"))),
        Case("diff3-one-change", "diff3", ("mine", "older", "yours"), 0,
             files=(("mine", b"a\nM\n"), ("older", b"a\nb\n"), ("yours", b"a\nb\n"))),
        Case("diff3-conflict", "diff3", ("mine", "older", "yours"), 0,
             files=(("mine", b"a\nM\n"), ("older", b"a\nb\n"), ("yours", b"a\nY\n"))),
        Case("diff3-ed", "diff3", ("-e", "mine", "older", "yours"), 0,
             files=(("mine", b"a\nM\n"), ("older", b"a\nb\n"), ("yours", b"a\nY\n"))),
        Case("diff3-merge", "diff3", ("-m", "mine", "older", "yours"), 1,
             files=(("mine", b"a\nM\n"), ("older", b"a\nb\n"), ("yours", b"a\nY\n"))),
        Case("diff3-labels", "diff3", ("-m", "-L", "OURS", "-L", "BASE", "-L", "THEIRS", "mine", "older", "yours"), 1,
             files=(("mine", b"M\n"), ("older", b"b\n"), ("yours", b"Y\n"))),
        Case("diff3-missing", "diff3", ("mine", "missing", "yours"), 2,
             files=(("mine", b"a\n"), ("yours", b"a\n"))),

        Case("sdiff-help", "sdiff", ("--help",), 0),
        Case("sdiff-version", "sdiff", ("--version",), 0),
        Case("sdiff-bad-option", "sdiff", ("--definitely-invalid",), 2),
        Case("sdiff-same", "sdiff", ("left", "right"), 0, files=same),
        Case("sdiff-different", "sdiff", ("left", "right"), 1, files=changed),
        Case("sdiff-width", "sdiff", ("-w", "40", "left", "right"), 1, files=changed),
        Case("sdiff-suppress-common", "sdiff", ("-s", "left", "right"), 1, files=changed),
        Case("sdiff-left-column", "sdiff", ("-l", "left", "right"), 1, files=changed),
        Case("sdiff-ignore-case", "sdiff", ("-i", "left", "right"), 0, files=changed),
        Case("sdiff-missing", "sdiff", ("missing", "right"), 2, files=(("right", b"x\n"),)),
    ]


def snapshot(root: Path, utility: str) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in sorted(root.rglob("*"), key=lambda item: os.fsencode(item.relative_to(root))):
        if path.name == utility and path.is_symlink():
            continue
        info = path.lstat()
        record: dict[str, object] = {
            "path": os.fsdecode(os.fsencode(path.relative_to(root))),
            "mode": stat.S_IMODE(info.st_mode),
            "kind": "directory" if path.is_dir() else "symlink" if path.is_symlink() else "file",
        }
        if path.is_symlink():
            record["target"] = os.readlink(path)
        elif path.is_file():
            payload = path.read_bytes()
            record.update(bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
        records.append(record)
    return records


def run(binary: Path, case: Case, root: Path) -> dict[str, object]:
    (root / case.utility).symlink_to(binary)
    for name, payload in case.files:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        os.utime(path, (1_600_000_000, 1_600_000_000))
    environment = dict(os.environ)
    environment.update({"LC_ALL": "C", "TZ": "UTC", "POSIXLY_CORRECT": "1"})
    result = subprocess.run(
        [f"./{case.utility}", *case.arguments], cwd=root, input=case.stdin,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment,
    )
    if result.returncode != case.expected_status:
        raise RuntimeError(
            f"{case.name}: status {result.returncode}, expected {case.expected_status}: "
            + result.stderr.decode(errors="replace")
        )
    (root / case.utility).unlink()
    return {
        "status": result.returncode,
        "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
        "tree": snapshot(root, case.utility),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    for utility in ("cmp", "diff", "diff3", "sdiff"):
        parser.add_argument(f"--gcc-{utility}", type=Path, required=True)
        parser.add_argument(f"--clang-{utility}", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = []
    with tempfile.TemporaryDirectory(prefix="rustbox-diffutils-differential-") as temporary:
        base = Path(temporary)
        for index, case in enumerate(cases()):
            gcc_root = base / f"{index:02d}-gcc"
            clang_root = base / f"{index:02d}-clang"
            gcc_root.mkdir()
            clang_root.mkdir()
            gcc = run(getattr(args, f"gcc_{case.utility}").resolve(), case, gcc_root)
            clang = run(getattr(args, f"clang_{case.utility}").resolve(), case, clang_root)
            if gcc != clang:
                raise RuntimeError(f"GCC/Clang mismatch: {case.name}\n{gcc}\n{clang}")
            records.append({"index": index, "name": case.name, "utility": case.utility,
                            "exact": True, "result": gcc})
    report = {"schema": 1, "comparisons": len(records), "gcc_clang_exact": True,
              "records": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"comparisons": len(records), "exact": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
