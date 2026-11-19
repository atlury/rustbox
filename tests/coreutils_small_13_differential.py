#!/usr/bin/env python3
"""Differential public and filesystem checks for Coreutils small batch 13."""

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
    ([], b""),
    ([b"node"], b""),
    ([b"node", b"x"], b""),
    ([b"node", b"c", b"bad", b"3"], b""),
    ([b"-m", b"invalid", b"node", b"p"], b""),
    ([b"-x"], b""),
]


def environment(locale: str, cwd: Path | None = None) -> dict[bytes, bytes]:
    env = os.environb.copy()
    for name in (b"LANG", b"LANGUAGE", b"LC_ALL", b"LC_MESSAGES", b"TZ"):
        env.pop(name, None)
    env[b"LC_ALL"] = locale.encode()
    env[b"TZ"] = b"UTC0"
    if cwd is not None:
        env[b"PWD"] = os.fsencode(cwd)
    return env


def command(binary: Path, link: Path, arguments: list[bytes], mode: str) -> list[bytes]:
    if mode == "explicit":
        return [os.fsencode(binary), b"--coreutils-prog=mknod", *arguments]
    link.unlink(missing_ok=True)
    link.symlink_to(binary)
    return [os.fsencode(link), *arguments]


def normalize_output(data: bytes, cwd: Path | None) -> bytes:
    return data if cwd is None else data.replace(os.fsencode(cwd), b"$CWD")


def run(
    binary: Path, link: Path, arguments: list[bytes], input_bytes: bytes,
    mode: str, locale: str, cwd: Path | None = None,
) -> tuple[int, bytes, bytes]:
    process = subprocess.run(
        command(binary, link, arguments, mode), cwd=cwd, env=environment(locale, cwd),
        input=input_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
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
                "uid": metadata.st_uid,
                "gid": metadata.st_gid,
            }
            if stat.S_ISFIFO(metadata.st_mode):
                record["kind"] = "fifo"
            elif stat.S_ISCHR(metadata.st_mode):
                record.update(kind="character", major=os.major(metadata.st_rdev), minor=os.minor(metadata.st_rdev))
            elif stat.S_ISBLK(metadata.st_mode):
                record.update(kind="block", major=os.major(metadata.st_rdev), minor=os.minor(metadata.st_rdev))
            elif stat.S_ISREG(metadata.st_mode):
                record.update(kind="regular", data=Path(os.fsdecode(path)).read_bytes().hex())
            elif stat.S_ISDIR(metadata.st_mode):
                record["kind"] = "directory"
            else:
                record["kind"] = "other"
            records.append(record)
    return records


Setup = Callable[[Path], tuple[list[bytes], bytes]]


def plain(arguments: list[bytes]) -> Setup:
    return lambda _directory: (arguments, b"")


def existing(directory: Path) -> tuple[list[bytes], bytes]:
    (directory / "node").write_bytes(b"existing")
    return [b"node", b"p"], b""


def raw_name(directory: Path) -> tuple[list[bytes], bytes]:
    return [b"raw-\xff", b"p"], b""


FILESYSTEM: list[tuple[str, Setup]] = [
    ("fifo", plain([b"node", b"p"])),
    ("numeric-mode", plain([b"-m", b"734", b"node", b"p"])),
    ("symbolic-mode", plain([b"--mode=ug+rw,o+r", b"node", b"p"])),
    ("character", plain([b"node", b"c", b"1", b"3"])),
    ("block", plain([b"node", b"b", b"7", b"0"])),
    ("existing", existing),
    ("missing-parent", plain([b"missing/node", b"p"])),
    ("raw-name", raw_name),
    ("restore-context", plain([b"-Z", b"node", b"p"])),
    ("explicit-context", plain([b"--context=abc", b"node", b"p"])),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--hybrid", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    canonical, hybrid = args.canonical.resolve(), args.hybrid.resolve()
    checked = 0
    with tempfile.TemporaryDirectory(prefix="rustbox-small-13-") as temporary:
        root = Path(temporary)
        link = root / "mknod"
        for locale in LOCALES:
            for mode in ("explicit", "argv0"):
                for arguments, input_bytes in [*STATELESS, *[(option, b"") for option in OPTIONS]]:
                    expected = run(canonical, link, arguments, input_bytes, mode, locale)
                    actual = run(hybrid, link, arguments, input_bytes, mode, locale)
                    if actual != expected:
                        raise AssertionError((locale, mode, arguments, expected, actual))
                    checked += 1

                for name, setup in FILESYSTEM:
                    pair = root / f"case-{checked}"
                    expected_dir, actual_dir = pair / "canonical", pair / "hybrid"
                    expected_dir.mkdir(parents=True)
                    actual_dir.mkdir()
                    expected_args, expected_input = setup(expected_dir)
                    actual_args, actual_input = setup(actual_dir)
                    expected = run(canonical, link, expected_args, expected_input, mode, locale, expected_dir)
                    actual = run(hybrid, link, actual_args, actual_input, mode, locale, actual_dir)
                    expected_tree, actual_tree = snapshot(expected_dir), snapshot(actual_dir)
                    if actual != expected or actual_tree != expected_tree:
                        raise AssertionError((locale, mode, name, expected, actual, expected_tree, actual_tree))
                    checked += 1

    result = {
        "schema": 1,
        "cases": checked,
        "passed": checked,
        "locales": LOCALES,
        "applets": ["mknod"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
