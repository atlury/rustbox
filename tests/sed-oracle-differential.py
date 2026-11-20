#!/usr/bin/env python3
"""Exact cross-compiler comparisons for the canonical GNU sed oracle."""

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
    arguments: tuple[str, ...]
    stdin: bytes = b""
    files: tuple[tuple[str, bytes], ...] = ()


def snapshot(root: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in sorted(root.rglob("*"), key=lambda p: os.fsencode(p.relative_to(root))):
        if path.name == "sed":
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
    (root / "sed").symlink_to(binary)
    for name, payload in case.files:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    environment = dict(os.environ)
    environment.update({"LC_ALL": "C", "TZ": "UTC", "POSIXLY_CORRECT": "1"})
    result = subprocess.run(
        ["./sed", *case.arguments], cwd=root, input=case.stdin,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment,
    )
    (root / "sed").unlink()
    return {
        "status": result.returncode,
        "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
        "tree": snapshot(root),
    }


def cases() -> list[Case]:
    lines = b"one\ntwo\nthree\nfour\n"
    return [
        Case("interface-help", ("--help",)),
        Case("interface-version", ("--version",)),
        Case("interface-bad-option", ("--definitely-invalid",)),
        Case("substitute-first", ("s/o/O/",), b"foo\nzoom\n"),
        Case("substitute-global", ("s/o/O/g",), b"foo\nzoom\n"),
        Case("quiet-print", ("-n", "2p"), lines),
        Case("range-delete", ("2,3d",), lines),
        Case("bre-groups", (r"s/\(one\)/[\1]/",), lines),
        Case("ere-groups", ("-E", "s/(one|two)/[&]/",), lines),
        Case("transliterate", ("y/ot/OT/",), lines),
        Case("hold-space", ("-n", "1h;2{x;p;x};$g;$p"), lines),
        Case("branch-label", (":a", "-e", "s/xx/x/", "-e", "ta"), b"xxxx\n"),
        Case("multiple-expressions", ("-e", "s/one/ONE/", "-e", "s/two/TWO/"), lines),
        Case("line-number", ("=",), b"a\nb\n"),
        Case("next-line", ("N;s/\\n/:/",), b"a\nb\nc\nd\n"),
        Case("nul-data", ("-z", "s/a/A/g"), b"a\x00ba\x00"),
        Case("script-file", ("-f", "script.sed", "input"), files=(("script.sed", b"s/o/O/g\n"), ("input", b"foo\n"))),
        Case("multiple-files", ("-n", "1p", "a", "b"), files=(("a", b"a1\na2\n"), ("b", b"b1\nb2\n"))),
        Case("separate-files", ("-s", "-n", "1p", "a", "b"), files=(("a", b"a1\na2\n"), ("b", b"b1\nb2\n"))),
        Case("in-place", ("-i", "s/old/new/", "input"), files=(("input", b"old\n"),)),
        Case("in-place-backup", ("-i.bak", "s/old/new/", "input"), files=(("input", b"old\n"),)),
        Case("invalid-command", ("qbroken",), b"input\n"),
        Case("missing-script", ("-f", "missing.sed")),
        Case("missing-input", ("p", "missing.input")),
        Case("sandbox-reject-read", ("--sandbox", "r /etc/passwd"), b"x\n"),
        Case("address-regexp", ("-n", "/two/p"), lines),
        Case("address-step", ("-n", "1~2p"), lines),
        Case("quit-status", ("2q7",), lines),
        Case("empty-input", ("p",), b""),
        Case("no-final-newline", ("s/x/y/",), b"x"),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gcc", type=Path, required=True)
    parser.add_argument("--clang", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = []
    with tempfile.TemporaryDirectory(prefix="rustbox-sed-differential-") as temporary:
        base = Path(temporary)
        for index, case in enumerate(cases()):
            gcc_root, clang_root = base / f"{index:02d}-gcc", base / f"{index:02d}-clang"
            gcc_root.mkdir(); clang_root.mkdir()
            gcc = run(args.gcc.resolve(), case, gcc_root)
            clang = run(args.clang.resolve(), case, clang_root)
            exact = gcc == clang
            records.append({"index": index, "name": case.name, "exact": exact, "result": gcc})
            if not exact:
                raise RuntimeError(f"GNU sed GCC/Clang mismatch: {case.name}\n{gcc}\n{clang}")
    report = {"schema": 1, "comparisons": len(records), "gcc_clang_exact": True, "records": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"comparisons": len(records), "exact": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
