#!/usr/bin/env python3
"""Differential public and filesystem checks for Coreutils small batch 15."""

from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Callable


LOCALES = ["C", "en_US.UTF-8", "fr_FR", "tr_TR.UTF-8", "ja_JP.EUC-JP"]
OPTIONS = [[b"--help"], [b"--version"]]
STATELESS = [
    [],
    [b"source"],
    [b"missing", b"destination"],
    [b"-d"],
    [b"--mode=invalid", b"source", b"destination"],
    [b"--owner=rustbox-no-such-user", b"source", b"destination"],
    [b"--group=rustbox-no-such-group", b"source", b"destination"],
    [b"-x"],
]


def environment(locale: str, cwd: Path | None = None) -> dict[bytes, bytes]:
    env = os.environb.copy()
    for name in (b"LANG", b"LANGUAGE", b"LC_ALL", b"LC_MESSAGES", b"TZ", b"VERSION_CONTROL"):
        env.pop(name, None)
    env[b"LC_ALL"] = locale.encode()
    env[b"TZ"] = b"UTC0"
    if cwd is not None:
        env[b"PWD"] = os.fsencode(cwd)
    return env


def command(binary: Path, link: Path, arguments: list[bytes], mode: str) -> list[bytes]:
    if mode == "explicit":
        return [os.fsencode(binary), b"--coreutils-prog=ginstall", *arguments]
    link.unlink(missing_ok=True)
    link.symlink_to(binary)
    return [os.fsencode(link), *arguments]


def normalize_output(data: bytes, cwd: Path | None) -> bytes:
    return data if cwd is None else data.replace(os.fsencode(cwd), b"$CWD")


def run(
    binary: Path, link: Path, arguments: list[bytes], mode: str,
    locale: str, cwd: Path | None = None,
) -> tuple[int, bytes, bytes]:
    process = subprocess.run(
        command(binary, link, arguments, mode), cwd=cwd, env=environment(locale, cwd),
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
    )
    return process.returncode, normalize_output(process.stdout, cwd), normalize_output(process.stderr, cwd)


def snapshot(directory: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    root = os.fsencode(directory)
    for current, directories, files in os.walk(root):
        directories.sort()
        files.sort()
        for name in [*directories, *files]:
            path = os.path.join(current, name)
            metadata = os.lstat(path)
            record: dict[str, object] = {
                "name": os.path.relpath(path, root).hex(),
                "mode": stat.S_IMODE(metadata.st_mode),
                "size": metadata.st_size,
                "links": metadata.st_nlink,
            }
            if stat.S_ISLNK(metadata.st_mode):
                record.update(kind="symlink", target=os.fsencode(os.readlink(path)).hex())
            elif stat.S_ISREG(metadata.st_mode):
                record.update(kind="regular", data=Path(os.fsdecode(path)).read_bytes().hex())
            elif stat.S_ISDIR(metadata.st_mode):
                record["kind"] = "directory"
            else:
                record["kind"] = "other"
            records.append(record)
    return records


Setup = Callable[[Path], list[bytes]]


def file_case(arguments: list[bytes], existing: bytes | None = None) -> Setup:
    def setup(directory: Path) -> list[bytes]:
        (directory / "source").write_bytes(b"alpha\x00beta\n")
        os.chmod(directory / "source", 0o640)
        os.utime(directory / "source", (946684800, 946684800))
        if existing is not None:
            (directory / "destination").write_bytes(existing)
            os.chmod(directory / "destination", 0o600)
        return arguments
    return setup


def directory_target(directory: Path) -> list[bytes]:
    (directory / "source").write_bytes(b"payload\n")
    (directory / "target").mkdir()
    return [b"source", b"target"]


def multiple(directory: Path) -> list[bytes]:
    (directory / "one").write_bytes(b"one\n")
    (directory / "two").write_bytes(b"two\n")
    (directory / "target").mkdir()
    return [b"-t", b"target", b"one", b"two"]


def create_leading(directory: Path) -> list[bytes]:
    (directory / "source").write_bytes(b"leading\n")
    return [b"-D", b"source", b"one/two/destination"]


def directories(directory: Path) -> list[bytes]:
    return [b"-d", b"one/two", b"three"]


def raw_name(directory: Path) -> list[bytes]:
    source = os.path.join(os.fsencode(directory), b"raw-\xff")
    destination = os.path.join(os.fsencode(directory), b"copy-\xfe")
    descriptor = os.open(source, os.O_WRONLY | os.O_CREAT, 0o640)
    os.write(descriptor, b"raw payload\n")
    os.close(descriptor)
    return [os.path.basename(source), os.path.basename(destination)]


def symlink_source(directory: Path) -> list[bytes]:
    (directory / "source").write_bytes(b"target payload\n")
    (directory / "link").symlink_to("source")
    return [b"link", b"destination"]


FILESYSTEM: list[tuple[str, Setup]] = [
    ("regular", file_case([b"source", b"destination"])),
    ("overwrite", file_case([b"source", b"destination"], b"old\n")),
    ("mode", file_case([b"-m", b"751", b"source", b"destination"])),
    ("symbolic-mode", file_case([b"-m", b"u=rw,go=r", b"source", b"destination"])),
    ("verbose", file_case([b"-v", b"source", b"destination"])),
    ("preserve-times", file_case([b"-p", b"source", b"destination"])),
    ("compare-same", file_case([b"-C", b"source", b"destination"], b"alpha\x00beta\n")),
    ("compare-different", file_case([b"-C", b"source", b"destination"], b"old\n")),
    ("backup", file_case([b"--backup=numbered", b"source", b"destination"], b"old\n")),
    ("no-target-directory", file_case([b"-T", b"source", b"destination"])),
    ("directory-target", directory_target),
    ("multiple", multiple),
    ("create-leading", create_leading),
    ("directories", directories),
    ("raw-name", raw_name),
    ("symlink-source", symlink_source),
    ("restore-context", file_case([b"-Z", b"source", b"destination"])),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--hybrid", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    canonical, hybrid = args.canonical.resolve(), args.hybrid.resolve()
    checked = 0
    with tempfile.TemporaryDirectory(prefix="rustbox-small-15-") as temporary:
        root = Path(temporary)
        link = root / "install"
        for locale in LOCALES:
            for mode in ("explicit", "argv0"):
                for arguments in [*STATELESS, *OPTIONS]:
                    expected = run(canonical, link, arguments, mode, locale)
                    actual = run(hybrid, link, arguments, mode, locale)
                    if actual != expected:
                        raise AssertionError((locale, mode, arguments, expected, actual))
                    checked += 1

                for name, setup in FILESYSTEM:
                    pair = root / f"case-{checked}"
                    expected_dir, actual_dir = pair / "canonical", pair / "hybrid"
                    expected_dir.mkdir(parents=True)
                    actual_dir.mkdir()
                    expected_args = setup(expected_dir)
                    actual_args = setup(actual_dir)
                    expected = run(canonical, link, expected_args, mode, locale, expected_dir)
                    actual = run(hybrid, link, actual_args, mode, locale, actual_dir)
                    expected_tree, actual_tree = snapshot(expected_dir), snapshot(actual_dir)
                    if actual != expected or actual_tree != expected_tree:
                        raise AssertionError((locale, mode, name, expected, actual, expected_tree, actual_tree))
                    checked += 1

    result = {
        "schema": 1,
        "cases": checked,
        "passed": checked,
        "locales": LOCALES,
        "applets": ["install"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
