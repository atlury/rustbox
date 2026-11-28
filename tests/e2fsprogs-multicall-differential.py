#!/usr/bin/env python3
"""Exact public-surface comparison for native E2fsprogs in Rustbox."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


PROGRAMS = (
    # canonical argv[0], Rustbox public name, canonical path, private engine
    ("badblocks", "badblocks", "sbin/badblocks", "badblocks"),
    ("debugfs", "debugfs", "sbin/debugfs", "debugfs"),
    ("dumpe2fs", "dumpe2fs", "sbin/dumpe2fs", "dumpe2fs"),
    ("e2fsck", "e2fsck", "sbin/e2fsck", "e2fsck"),
    ("e2image", "e2image", "sbin/e2image", "e2image"),
    ("e2label", "e2label", "sbin/e2label", "tune2fs"),
    ("e2mmpstatus", "e2mmpstatus", "sbin/e2mmpstatus", "dumpe2fs"),
    ("e2undo", "e2undo", "sbin/e2undo", "e2undo"),
    ("fsck", "e2fsprogs-fsck", "sbin/fsck", "fsck"),
    ("fsck.ext2", "fsck.ext2", "sbin/fsck.ext2", "e2fsck"),
    ("fsck.ext3", "fsck.ext3", "sbin/fsck.ext3", "e2fsck"),
    ("fsck.ext4", "fsck.ext4", "sbin/fsck.ext4", "e2fsck"),
    ("logsave", "logsave", "sbin/logsave", "logsave"),
    ("mke2fs", "mke2fs", "sbin/mke2fs", "mke2fs"),
    ("mkfs.ext2", "mkfs.ext2", "sbin/mkfs.ext2", "mke2fs"),
    ("mkfs.ext3", "mkfs.ext3", "sbin/mkfs.ext3", "mke2fs"),
    ("mkfs.ext4", "mkfs.ext4", "sbin/mkfs.ext4", "mke2fs"),
    ("resize2fs", "resize2fs", "sbin/resize2fs", "resize2fs"),
    ("tune2fs", "tune2fs", "sbin/tune2fs", "tune2fs"),
    ("chattr", "chattr", "usr/bin/chattr", "chattr"),
    ("fuse2fs", "fuse2fs", "usr/bin/fuse2fs", "fuse2fs"),
    ("lsattr", "lsattr", "usr/bin/lsattr", "lsattr"),
    ("e2initrd_helper", "e2initrd_helper", "usr/lib/e2initrd_helper", "e2initrd_helper"),
    ("e2freefrag", "e2freefrag", "usr/sbin/e2freefrag", "e2freefrag"),
    ("e4crypt", "e4crypt", "usr/sbin/e4crypt", "e4crypt"),
    ("e4defrag", "e4defrag", "usr/sbin/e4defrag", "e4defrag"),
    ("filefrag", "filefrag", "usr/sbin/filefrag", "filefrag"),
    ("mklost+found", "mklost+found", "usr/sbin/mklost+found", "mklost_found"),
)
CASES = ((), ("--help",), ("-V",))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot(directory: Path) -> list[dict[str, object]]:
    records = []
    for path in sorted(directory.rglob("*")):
        status = path.lstat()
        records.append({
            "path": path.relative_to(directory).as_posix(),
            "kind": (
                "symlink" if path.is_symlink()
                else "directory" if path.is_dir()
                else "file"
            ),
            "mode": status.st_mode & 0o7777,
            "bytes": status.st_size if path.is_file() else None,
            "sha256": sha256(path.read_bytes()) if path.is_file() else None,
            "target": os.readlink(path) if path.is_symlink() else None,
        })
    return records


def invoke(
    command: list[str], executable: Path, environment: dict[str, str],
    replacements: tuple[tuple[bytes, bytes], ...],
) -> tuple[int | str, bytes, bytes, list[dict[str, object]]]:
    with tempfile.TemporaryDirectory(prefix="rustbox-e2fsprogs-multicall-") as temporary:
        directory = Path(temporary)
        try:
            process = subprocess.run(
                command, executable=executable, cwd=directory, env=environment,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=10, check=False,
            )
            status: int | str = process.returncode
            stdout, stderr = process.stdout, process.stderr
        except subprocess.TimeoutExpired as error:
            status = "timeout"
            stdout, stderr = error.stdout or b"", error.stderr or b""
        for before, after in replacements:
            stdout = stdout.replace(before, after)
            stderr = stderr.replace(before, after)
        return status, stdout, stderr, snapshot(directory)


def summary(result: tuple[int | str, bytes, bytes, object]) -> dict[str, object]:
    status, stdout, stderr, filesystem = result
    return {
        "status": status,
        "stdout_bytes": len(stdout),
        "stdout_sha256": sha256(stdout),
        "stderr_bytes": len(stderr),
        "stderr_sha256": sha256(stderr),
        "filesystem": filesystem,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-root", required=True, type=Path)
    parser.add_argument("--rustbox", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    canonical_root = args.canonical_root.resolve()
    rustbox = args.rustbox.resolve()
    environment = os.environ.copy()
    environment.update({
        "LC_ALL": "C", "LANG": "C", "LANGUAGE": "C", "TZ": "UTC",
        "PATH": ":".join(
            str(canonical_root / name)
            for name in ("sbin", "usr/sbin", "usr/bin", "usr/lib")
        ) + ":/usr/sbin:/usr/bin:/sbin:/bin",
    })
    records = []
    for canonical_name, public_name, relative, engine in PROGRAMS:
        canonical = canonical_root / relative
        if not canonical.is_file() or not rustbox.is_file():
            raise RuntimeError(f"missing comparison input: {canonical} or {rustbox}")
        for arguments in CASES:
            expected = invoke(
                [canonical_name, *arguments], canonical, environment,
                ((str(canonical).encode(), canonical_name.encode()),
                 (str(canonical_root).encode(), b"<ROOT>")),
            )
            actual = invoke(
                [str(rustbox), public_name, *arguments], rustbox, environment,
                ((str(rustbox).encode(), canonical_name.encode()),),
            )
            passed = isinstance(expected[0], int) and expected == actual
            records.append({
                "program": public_name,
                "canonical_name": canonical_name,
                "dispatch_name": public_name,
                "engine": engine,
                "arguments": list(arguments),
                "passed": passed,
                "canonical": summary(expected),
                "multicall": summary(actual),
            })
            if not passed:
                raise RuntimeError(
                    f"E2fsprogs multicall mismatch: {public_name} {arguments}: "
                    f"canonical={expected!r} multicall={actual!r}"
                )

    result = {
        "schema": 1,
        "release": "1.47.4",
        "native_names": len(PROGRAMS),
        "native_engines": len({engine for _, _, _, engine in PROGRAMS}),
        "cases": len(records),
        "passed": sum(record["passed"] for record in records),
        "collision_aliases": {"fsck": "e2fsprogs-fsck"},
        "canonical_multicall_exact": True,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        key: result[key]
        for key in ("native_names", "native_engines", "cases", "passed")
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
