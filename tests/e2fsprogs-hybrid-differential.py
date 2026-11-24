#!/usr/bin/env python3
"""Exact public-surface comparison for translated E2fsprogs closures."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


PROGRAMS = (
    ("sbin/badblocks", "badblocks", "badblocks"),
    ("sbin/debugfs", "debugfs", "debugfs"),
    ("sbin/dumpe2fs", "dumpe2fs", "dumpe2fs"),
    ("sbin/e2fsck", "e2fsck", "e2fsck"),
    ("sbin/e2image", "e2image", "e2image"),
    ("sbin/e2label", "e2label", "tune2fs"),
    ("sbin/e2mmpstatus", "e2mmpstatus", "dumpe2fs"),
    ("sbin/e2undo", "e2undo", "e2undo"),
    ("sbin/fsck", "fsck", "fsck"),
    ("sbin/fsck.ext2", "fsck.ext2", "e2fsck"),
    ("sbin/fsck.ext3", "fsck.ext3", "e2fsck"),
    ("sbin/fsck.ext4", "fsck.ext4", "e2fsck"),
    ("sbin/logsave", "logsave", "logsave"),
    ("sbin/mke2fs", "mke2fs", "mke2fs"),
    ("sbin/mkfs.ext2", "mkfs.ext2", "mke2fs"),
    ("sbin/mkfs.ext3", "mkfs.ext3", "mke2fs"),
    ("sbin/mkfs.ext4", "mkfs.ext4", "mke2fs"),
    ("sbin/resize2fs", "resize2fs", "resize2fs"),
    ("sbin/tune2fs", "tune2fs", "tune2fs"),
    ("usr/bin/chattr", "chattr", "chattr"),
    ("usr/bin/fuse2fs", "fuse2fs", "fuse2fs"),
    ("usr/bin/lsattr", "lsattr", "lsattr"),
    ("usr/lib/e2initrd_helper", "e2initrd_helper", "e2initrd_helper"),
    ("usr/sbin/e2freefrag", "e2freefrag", "e2freefrag"),
    ("usr/sbin/e4crypt", "e4crypt", "e4crypt"),
    ("usr/sbin/e4defrag", "e4defrag", "e4defrag"),
    ("usr/sbin/filefrag", "filefrag", "filefrag"),
    ("usr/sbin/mklost+found", "mklost+found", "mklost_found"),
)
CASES = ((), ("--help",), ("-V",), ("--rustbox-invalid-option",))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(root: Path) -> list[dict[str, object]]:
    records = []
    for path in sorted(root.rglob("*")):
        status = path.lstat()
        records.append({
            "path": str(path.relative_to(root)),
            "kind": (
                "symlink" if path.is_symlink()
                else "directory" if path.is_dir()
                else "file"
            ),
            "mode": status.st_mode & 0o7777,
            "size": status.st_size if path.is_file() else None,
            "sha256": sha256(path) if path.is_file() else None,
            "target": os.readlink(path) if path.is_symlink() else None,
        })
    return records


def invoke(
    binary: Path, name: str, arguments: tuple[str, ...], search: tuple[Path, ...]
) -> dict[str, object]:
    environment = os.environ.copy()
    environment.update({
        "LC_ALL": "C",
        "LANG": "C",
        "TZ": "UTC",
        "PATH": ":".join(str(path) for path in search) + ":/usr/sbin:/usr/bin:/sbin:/bin",
    })
    with tempfile.TemporaryDirectory(prefix="rustbox-e2fsprogs-hybrid-") as temporary:
        directory = Path(temporary)
        try:
            process = subprocess.run(
                [name, *arguments], executable=binary,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, cwd=directory, env=environment,
                timeout=10, check=False,
            )
            status: int | str = process.returncode
            stdout = process.stdout
            stderr = process.stderr
        except subprocess.TimeoutExpired as error:
            status = "timeout"
            stdout = error.stdout or b""
            stderr = error.stderr or b""
        replacements = (
            (str(binary.parent).encode(), b"<PROGRAMS>"),
            (str(directory).encode(), b"<TMP>"),
        )
        for before, after in replacements:
            stdout = stdout.replace(before, after)
            stderr = stderr.replace(before, after)
        return {
            "status": status,
            "stdout_hex": stdout.hex(),
            "stderr_hex": stderr.hex(),
            "filesystem": snapshot(directory),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-root", required=True, type=Path)
    parser.add_argument("--hybrid-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    canonical_root = args.canonical_root.resolve()
    hybrid_root = args.hybrid_root.resolve()
    canonical_search = tuple(
        canonical_root / relative
        for relative in ("sbin", "usr/sbin", "usr/bin", "usr/lib")
    )
    hybrid_search = (hybrid_root,)

    records = []
    for relative, name, engine in PROGRAMS:
        for arguments in CASES:
            canonical = invoke(
                canonical_root / relative, name, arguments, canonical_search
            )
            # Launch the public spelling, including every symlink alias, while
            # forcing argv[0] to the same spelling used by the canonical tree.
            hybrid = invoke(hybrid_root / name, name, arguments, hybrid_search)
            passed = canonical == hybrid
            records.append({
                "program": name,
                "engine": engine,
                "arguments": list(arguments),
                "passed": passed,
                "canonical": canonical,
                "hybrid": hybrid,
            })
            if not passed:
                raise RuntimeError(
                    f"E2fsprogs hybrid mismatch: {name} {arguments}: "
                    f"canonical={canonical!r} hybrid={hybrid!r}"
                )

    result = {
        "schema": 1,
        "release": "1.47.4",
        "public_names": len(PROGRAMS),
        "engines": len({engine for _, _, engine in PROGRAMS}),
        "cases": len(records),
        "passed": len(records),
        "canonical_hybrid_exact": True,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(
        {key: result[key] for key in ("public_names", "engines", "cases", "passed")},
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
