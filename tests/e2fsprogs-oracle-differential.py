#!/usr/bin/env python3
"""Compare every installed E2fsprogs frontend across independent compilers."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path


CASES = ((), ("--help",), ("-V",))


def run(root: Path, relative: str, arguments: tuple[str, ...]) -> dict[str, object]:
    executable = root / relative
    environment = os.environ.copy()
    environment.update({
        "LC_ALL": "C",
        "LANG": "C",
        "PATH": ":".join(str(root / name) for name in ("sbin", "usr/sbin", "usr/bin", "usr/lib"))
        + ":/usr/sbin:/usr/bin:/sbin:/bin",
    })
    with tempfile.TemporaryDirectory(prefix="rustbox-e2fsprogs-diff-") as temporary:
        try:
            result = subprocess.run(
                [str(executable), *arguments], stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=temporary, env=environment, timeout=10, check=False,
            )
            status = result.returncode
            stdout = result.stdout
            stderr = result.stderr
        except subprocess.TimeoutExpired as error:
            status = "timeout"
            stdout = error.stdout or b""
            stderr = error.stderr or b""
        root_bytes = str(root).encode()
        snapshot = []
        for path in sorted(Path(temporary).rglob("*")):
            stat = path.lstat()
            snapshot.append({
                "path": str(path.relative_to(temporary)),
                "kind": "symlink" if path.is_symlink() else "directory" if path.is_dir() else "file",
                "mode": stat.st_mode & 0o7777,
                "size": stat.st_size if path.is_file() else None,
                "target": os.readlink(path) if path.is_symlink() else None,
            })
        return {
            "status": status,
            "stdout_hex": stdout.replace(root_bytes, b"<ORACLE>").hex(),
            "stderr_hex": stderr.replace(root_bytes, b"<ORACLE>").hex(),
            "filesystem": snapshot,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gcc-root", required=True, type=Path)
    parser.add_argument("--clang-root", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    programs = tuple(line.strip() for line in args.inventory.read_text().splitlines() if line.strip())
    records = []
    for relative in programs:
        for arguments in CASES:
            gcc = run(args.gcc_root, relative, arguments)
            clang = run(args.clang_root, relative, arguments)
            records.append({
                "program": relative,
                "arguments": list(arguments),
                "gcc": gcc,
                "clang": clang,
                "passed": gcc == clang,
            })
    result = {
        "schema": 1,
        "programs": len(programs),
        "cases": len(records),
        "passed": sum(record["passed"] for record in records),
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: result[key] for key in ("programs", "cases", "passed")}, sort_keys=True))
    return 0 if result["passed"] == result["cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
