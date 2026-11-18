#!/usr/bin/env python3
"""Download, hash-check, and safely extract pinned Rustbox upstreams."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def download(url: str, destination: Path, offline: bool) -> None:
    if destination.exists():
        return
    if offline:
        raise RuntimeError(f"offline and missing {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=destination.name + ".", suffix=".part", dir=destination.parent, delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
        try:
            with urllib.request.urlopen(url) as response:
                shutil.copyfileobj(response, temporary)
            temporary.flush()
            os.fsync(temporary.fileno())
            os.replace(temporary_path, destination)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise


def within(root: Path, candidate: Path) -> bool:
    try:
        return os.path.commonpath((root, candidate)) == str(root)
    except ValueError:
        return False


def validate_members(archive: tarfile.TarFile, destination: Path) -> None:
    root = destination.resolve()
    for member in archive.getmembers():
        target = (root / member.name).resolve()
        if not within(root, target):
            raise RuntimeError(f"archive path escapes extraction root: {member.name}")
        if member.issym():
            link = (target.parent / member.linkname).resolve()
            if not within(root, link):
                raise RuntimeError(f"archive symlink escapes extraction root: {member.name}")
        elif member.islnk():
            link = (root / member.linkname).resolve()
            if not within(root, link):
                raise RuntimeError(f"archive hard link escapes extraction root: {member.name}")


def extract(archive_path: Path, source_directory: str, destination_root: Path) -> Path:
    destination = destination_root / source_directory
    if destination.exists():
        return destination
    destination_root.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(tempfile.mkdtemp(prefix=".extract-", dir=destination_root))
    try:
        with tarfile.open(archive_path, "r:xz") as archive:
            validate_members(archive, temporary_root)
            archive.extractall(temporary_root)
        extracted = temporary_root / source_directory
        if not extracted.is_dir():
            raise RuntimeError(f"archive lacks expected root {source_directory}")
        os.replace(extracted, destination)
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)
    return destination


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("packages", nargs="*")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()

    manifest = json.loads((root / "upstream/releases.json").read_text(encoding="utf-8"))
    releases = manifest["releases"]
    selected = args.packages or list(releases)
    unknown = sorted(set(selected) - set(releases))
    if unknown:
        parser.error("unknown packages: " + ", ".join(unknown))

    cache = root / ".cache/downloads"
    sources = root / "work/upstream"
    state_directory = sources / ".state"
    state_directory.mkdir(parents=True, exist_ok=True)
    for name in selected:
        release = releases[name]
        archive_path = cache / release["archive"]
        signature_path = cache / (release["archive"] + ".signature")
        key_path = cache / release["key"]
        download(release["url"], archive_path, args.offline)
        actual = digest(archive_path)
        if actual != release["sha256"]:
            raise RuntimeError(
                f"{name}: SHA-256 {actual}, expected {release['sha256']}"
            )
        download(release["signature_url"], signature_path, args.offline)
        signature_digest = digest(signature_path)
        if signature_digest != release["signature_sha256"]:
            raise RuntimeError(
                f"{name}: signature SHA-256 {signature_digest}, "
                f"expected {release['signature_sha256']}"
            )
        download(release["key_url"], key_path, args.offline)
        key_digest = digest(key_path)
        if key_digest != release["key_sha256"]:
            raise RuntimeError(
                f"{name}: key SHA-256 {key_digest}, expected {release['key_sha256']}"
            )
        destination = extract(archive_path, release["source_directory"], sources)
        state = {
            "name": name,
            "version": release["version"],
            "archive": release["archive"],
            "sha256": actual,
            "source": str(destination.relative_to(root)),
            "signature": str(signature_path.relative_to(root)),
            "signature_sha256": signature_digest,
            "signer_fingerprint": release["signer_fingerprint"],
            "key": str(key_path.relative_to(root)),
            "key_sha256": key_digest,
            "signature_verified": False,
        }
        (state_directory / f"{name}.json").write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"{name} {release['version']}: {actual}")

    print(
        "Detached signatures and pinned keys downloaded; run "
        "scripts/verify_signatures.py in the tool container.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

