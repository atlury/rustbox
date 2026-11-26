#!/usr/bin/env python3
"""Exact cross-compiler comparisons for the canonical GNU patch oracle."""

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
    patch: bytes
    files: tuple[tuple[str, bytes], ...] = ()
    stdin: bool = False


def snapshot(root: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in sorted(root.rglob("*"), key=lambda item: os.fsencode(item.relative_to(root))):
        relative = os.fsdecode(os.fsencode(path.relative_to(root)))
        info = path.lstat()
        record: dict[str, object] = {
            "path": relative,
            "mode": stat.S_IMODE(info.st_mode),
            "kind": "directory" if path.is_dir() else "symlink" if path.is_symlink() else "file",
        }
        if path.is_symlink():
            record["target"] = os.readlink(path)
        elif path.is_file():
            record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            record["bytes"] = path.stat().st_size
        records.append(record)
    return records


def run(binary: Path, case: Case, root: Path, argv_zero: str = "./patch") -> dict[str, object]:
    runner = root / "patch"
    runner.symlink_to(binary)
    for name, payload in case.files:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    patch_file = root / "change.patch"
    patch_file.write_bytes(case.patch)
    arguments = list(case.arguments)
    input_bytes = None
    if case.stdin:
        input_bytes = case.patch
    else:
        arguments = ["-i", "change.patch", *arguments]
    environment = dict(os.environ)
    environment.update({"LC_ALL": "C", "TZ": "UTC", "POSIXLY_CORRECT": "1"})
    result = subprocess.run(
        [argv_zero, *arguments],
        executable="./patch",
        cwd=root,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
    )
    runner.unlink()
    patch_file.unlink(missing_ok=True)
    return {
        "status": result.returncode,
        "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
        "tree": snapshot(root),
    }


def cases() -> list[Case]:
    unified = b"--- alpha\n+++ alpha\n@@ -1,2 +1,2 @@\n-old\n+new\n keep\n"
    context = b"*** alpha\t2020-01-01\n--- alpha\t2020-01-01\n***************\n*** 1,2 ****\n! old\n  keep\n--- 1,2 ----\n! new\n  keep\n"
    normal = b"1c1\n< old\n---\n> new\n"
    return [
        Case("interface-help", ("--help",), b""),
        Case("interface-version", ("--version",), b""),
        Case("interface-bad-option", ("--definitely-invalid",), b""),
        Case("unified-file", (), unified, (("alpha", b"old\nkeep\n"),)),
        Case("unified-stdin", (), unified, (("alpha", b"old\nkeep\n"),), True),
        Case("context", (), context, (("alpha", b"old\nkeep\n"),)),
        Case("normal", ("alpha",), normal, (("alpha", b"old\n"),)),
        Case("reverse", ("-R",), unified, (("alpha", b"new\nkeep\n"),)),
        Case("dry-run", ("--dry-run",), unified, (("alpha", b"old\nkeep\n"),)),
        Case("force", ("-f",), unified, (("alpha", b"old\nkeep\n"),)),
        Case("batch", ("-t",), unified, (("alpha", b"old\nkeep\n"),)),
        Case("silent", ("-s",), unified, (("alpha", b"old\nkeep\n"),)),
        Case("strip-one", ("-p1",), b"--- a/alpha\n+++ b/alpha\n@@ -1 +1 @@\n-old\n+new\n", (("alpha", b"old\n"),)),
        Case("directory-prefix", ("-d", "tree"), unified, (("tree/alpha", b"old\nkeep\n"),)),
        Case("backup", ("-b", "--suffix=.orig"), unified, (("alpha", b"old\nkeep\n"),)),
        Case("reject", (), b"--- alpha\n+++ alpha\n@@ -1 +1 @@\n-missing\n+new\n", (("alpha", b"old\n"),)),
        Case("reject-custom", ("-r", "failure.rej"), b"--- alpha\n+++ alpha\n@@ -1 +1 @@\n-missing\n+new\n", (("alpha", b"old\n"),)),
        Case("create", (), b"--- /dev/null\n+++ created\n@@ -0,0 +1,2 @@\n+one\n+two\n"),
        Case("delete", (), b"--- doomed\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-one\n-two\n", (("doomed", b"one\ntwo\n"),)),
        Case("remove-empty", ("-E",), b"--- empty\n+++ empty\n@@ -1 +0,0 @@\n-only\n", (("empty", b"only\n"),)),
        Case("ifdef", ("-D", "RUSTBOX"), unified, (("alpha", b"old\nkeep\n"),)),
        Case("fuzz", ("-F", "2"), b"--- alpha\n+++ alpha\n@@ -1,3 +1,3 @@\n wrong-context\n-old\n+new\n keep\n", (("alpha", b"different-context\nold\nkeep\n"),)),
        Case("offset", (), b"--- alpha\n+++ alpha\n@@ -1,2 +1,2 @@\n-old\n+new\n keep\n", (("alpha", b"prefix\nold\nkeep\n"),)),
        Case("space-name", (), b"--- a file\n+++ a file\n@@ -1 +1 @@\n-old\n+new\n", (("a file", b"old\n"),)),
        Case("no-newline", (), b"--- alpha\n+++ alpha\n@@ -1 +1 @@\n-old\n\\ No newline at end of file\n+new\n\\ No newline at end of file\n", (("alpha", b"old"),)),
        Case("two-files", (), b"--- alpha\n+++ alpha\n@@ -1 +1 @@\n-a\n+A\n--- beta\n+++ beta\n@@ -1 +1 @@\n-b\n+B\n", (("alpha", b"a\n"), ("beta", b"b\n"))),
        Case("merge", ("--merge",), b"--- alpha\n+++ alpha\n@@ -1,3 +1,3 @@\n one\n-old\n+new\n three\n", (("alpha", b"one\nlocal\nthree\n"),)),
        Case("merge-diff3", ("--merge=diff3",), b"--- alpha\n+++ alpha\n@@ -1,3 +1,3 @@\n one\n-old\n+new\n three\n", (("alpha", b"one\nlocal\nthree\n"),)),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gcc", type=Path, required=True)
    parser.add_argument("--clang", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--argv-zero", choices=("./patch", "patch"), default="./patch")
    args = parser.parse_args()
    records = []
    with tempfile.TemporaryDirectory(prefix="rustbox-patch-differential-") as temporary:
        base = Path(temporary)
        for index, case in enumerate(cases()):
            gcc_root = base / f"{index:02d}-gcc"
            clang_root = base / f"{index:02d}-clang"
            gcc_root.mkdir()
            clang_root.mkdir()
            gcc = run(args.gcc.resolve(), case, gcc_root, args.argv_zero)
            clang = run(args.clang.resolve(), case, clang_root, args.argv_zero)
            exact = gcc == clang
            records.append({"index": index, "name": case.name, "exact": exact, "result": gcc})
            if not exact:
                raise RuntimeError(f"GNU patch GCC/Clang mismatch: {case.name}\n{gcc}\n{clang}")
    report = {"schema": 1, "comparisons": len(records), "gcc_clang_exact": True, "records": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"comparisons": len(records), "exact": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
