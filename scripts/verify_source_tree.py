#!/usr/bin/env python3
"""Prove an extracted upstream tree still matches its pinned release archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tarfile
from pathlib import Path


def file_digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("package")
    args = parser.parse_args()

    releases = json.loads((root / "upstream/releases.json").read_text())["releases"]
    if args.package not in releases:
        parser.error(f"unknown package: {args.package}")
    release = releases[args.package]
    archive_path = root / ".cache/downloads" / release["archive"]
    source_root = root / "work/upstream" / release["source_directory"]
    if not archive_path.is_file() or not source_root.is_dir():
        raise RuntimeError("run scripts/fetch_upstreams.py first")

    expected: set[str] = set()
    checked = 0
    prefix = release["source_directory"] + "/"
    with tarfile.open(archive_path, "r:*") as archive:
        for member in archive.getmembers():
            if member.name == release["source_directory"]:
                continue
            if not member.name.startswith(prefix):
                raise RuntimeError(f"unexpected archive member: {member.name}")
            relative = member.name[len(prefix) :].rstrip("/")
            if not relative:
                continue
            expected.add(relative)
            path = source_root / relative
            if member.isdir():
                if not path.is_dir():
                    raise RuntimeError(f"missing or changed directory: {relative}")
            elif member.issym():
                if not path.is_symlink() or os.readlink(path) != member.linkname:
                    raise RuntimeError(f"changed symbolic link: {relative}")
            elif member.isfile() or member.islnk():
                if not path.is_file() or path.is_symlink():
                    raise RuntimeError(f"missing or changed file: {relative}")
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise RuntimeError(f"cannot read archive member: {relative}")
                digest = hashlib.sha256(extracted.read()).hexdigest()
                if file_digest(path) != digest:
                    raise RuntimeError(f"content changed: {relative}")
            else:
                raise RuntimeError(f"unsupported archive member type: {relative}")
            checked += 1

    actual = {
        str(path.relative_to(source_root))
        for path in source_root.rglob("*")
    }
    extras = sorted(actual - expected)
    missing = sorted(expected - actual)
    if extras or missing:
        raise RuntimeError(f"tree mismatch: extra={extras[:10]} missing={missing[:10]}")
    print(f"{args.package}: {checked} archive members match exactly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
