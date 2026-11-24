#!/usr/bin/env python3
"""Download, hash-check, extract, and record the signed E2fsprogs source."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path


VERSION = "1.47.4"
ARCHIVE = f"e2fsprogs-{VERSION}.tar.xz"
ARCHIVE_URL = f"https://cdn.kernel.org/pub/linux/kernel/people/tytso/e2fsprogs/v{VERSION}/{ARCHIVE}"
ARCHIVE_SHA256 = "fd5bf388cbdbe006a3d3b318d983b2948382440acc85a87f1e7d108653e8db0b"
SIGNATURE_URL = f"https://cdn.kernel.org/pub/linux/kernel/people/tytso/e2fsprogs/v{VERSION}/e2fsprogs-{VERSION}.tar.sign"
SIGNATURE_SHA256 = "ff826cf86828bf3ed8a7fcbe3e5c0c171f8ebfc5f46c43b27adc1ffc2c6a7b9c"
KEY_URL = "https://keys.openpgp.org/vks/v1/by-fingerprint/2B69B954DBFE0879288137C9F2F95956950D81A3"
KEY_SHA256 = "aefee846527b1ac909a61d1251f0ba67ca66fd5a3be66d97169f5dc18d1720f9"
SIGNER = "2B69B954DBFE0879288137C9F2F95956950D81A3"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def download(url: str, destination: Path) -> None:
    if destination.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as temporary:
        staged = Path(temporary.name)
        try:
            with urllib.request.urlopen(url) as response:
                shutil.copyfileobj(response, temporary)
            temporary.flush()
            os.fsync(temporary.fileno())
            os.replace(staged, destination)
        except BaseException:
            staged.unlink(missing_ok=True)
            raise


def verify_tree(archive_path: Path, source: Path) -> int:
    expected = set()
    prefix = f"e2fsprogs-{VERSION}/"
    checked = 0
    with tarfile.open(archive_path, "r:xz") as archive:
        for member in archive.getmembers():
            if member.name.rstrip("/") == prefix.rstrip("/"):
                continue
            if not member.name.startswith(prefix):
                raise RuntimeError(f"unexpected archive member: {member.name}")
            relative = member.name[len(prefix):].rstrip("/")
            if not relative:
                continue
            expected.add(relative)
            path = source / relative
            if member.isdir():
                if not path.is_dir():
                    raise RuntimeError(f"changed directory: {relative}")
            elif member.issym():
                if not path.is_symlink() or os.readlink(path) != member.linkname:
                    raise RuntimeError(f"changed symlink: {relative}")
            elif member.isfile() or member.islnk():
                if not path.is_file() or path.is_symlink():
                    raise RuntimeError(f"changed file: {relative}")
                extracted = archive.extractfile(member)
                if extracted is None or hashlib.sha256(extracted.read()).hexdigest() != digest(path):
                    raise RuntimeError(f"changed content: {relative}")
            else:
                raise RuntimeError(f"unsupported archive member: {relative}")
            checked += 1
    actual = {str(path.relative_to(source)) for path in source.rglob("*")}
    if actual != expected:
        raise RuntimeError(
            f"source tree mismatch: extra={sorted(actual - expected)[:10]} "
            f"missing={sorted(expected - actual)[:10]}"
        )
    return checked


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("download", "extract-verified"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    cache = root / ".cache/downloads"
    archive = cache / ARCHIVE
    signature = cache / f"{ARCHIVE}.signature"
    key = cache / "e2fsprogs-release-key.asc"
    artifacts = (
        (ARCHIVE_URL, archive, ARCHIVE_SHA256),
        (SIGNATURE_URL, signature, SIGNATURE_SHA256),
        (KEY_URL, key, KEY_SHA256),
    )
    for url, path, expected in artifacts:
        download(url, path)
        if digest(path) != expected:
            raise RuntimeError(f"E2fsprogs authentication artifact changed: {path.name}")
    if args.phase == "download":
        return 0

    source = root / "work/upstream" / f"e2fsprogs-{VERSION}"
    if not source.exists():
        from fetch_upstreams import extract
        extract(archive, f"e2fsprogs-{VERSION}", source.parent)
    checked = verify_tree(archive, source)
    state = {
        "schema": 1,
        "name": "e2fsprogs",
        "version": VERSION,
        "source_kind": "signed-release-archive",
        "archive": ARCHIVE,
        "sha256": ARCHIVE_SHA256,
        "signature": str(signature.relative_to(root)),
        "signature_sha256": SIGNATURE_SHA256,
        "signature_mode": "uncompressed-tar",
        "signer_fingerprint": SIGNER,
        "key": str(key.relative_to(root)),
        "key_sha256": KEY_SHA256,
        "signature_verified": True,
        "source": str(source.relative_to(root)),
        "archive_members_verified": checked,
    }
    state_path = root / "work/upstream/.state/e2fsprogs.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"members": checked, "sha256": ARCHIVE_SHA256}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
