#!/usr/bin/env python3
"""Differential public and CPU-dispatch checks for Coreutils small batch 10."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable


LOCALES = ["C", "en_US.UTF-8", "fr_FR", "tr_TR.UTF-8", "ja_JP.EUC-JP"]
ALGORITHMS = [
    b"bsd", b"sysv", b"crc", b"crc32b", b"md5", b"sha1", b"sha224",
    b"sha256", b"sha384", b"sha512", b"sha2", b"sha3", b"blake2b", b"sm3",
]
INPUTS = [b"", b"abc\n", bytes(range(256)) * 3]
OPTIONS = [[b"--help"], [b"--version"]]
STATELESS = [
    ([], b""),
    ([b"-a", b"invalid"], b"abc"),
    ([b"-l", b"7", b"-a", b"sha3"], b"abc"),
    ([b"--raw", b"--base64"], b"abc"),
    ([b"--check"], b"not a checksum\n"),
    ([b"--check", b"--raw"], b""),
    ([b"--algorithm=crc", b"--length=32"], b"abc"),
    ([b"-x"], b""),
] + [([b"--algorithm=" + algorithm], data) for algorithm in ALGORITHMS for data in INPUTS]


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
        return [os.fsencode(binary), b"--coreutils-prog=cksum", *arguments]
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


Setup = Callable[[Path], tuple[list[bytes], bytes]]


def files(arguments: list[bytes], large: bool = False, raw: bool = False) -> Setup:
    def setup(directory: Path) -> tuple[list[bytes], bytes]:
        name = b"raw-\xff" if raw else b"input"
        path = os.path.join(os.fsencode(directory), name)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT, 0o640)
        payload = (bytes(range(256)) * 4096) if large else b"alpha\x00beta\n"
        os.write(descriptor, payload)
        os.close(descriptor)
        return [*arguments, name], b""
    return setup


def two_files(arguments: list[bytes]) -> Setup:
    def setup(directory: Path) -> tuple[list[bytes], bytes]:
        (directory / "one").write_bytes(b"one\n")
        (directory / "two").write_bytes(b"two\n")
        return [*arguments, b"one", b"two"], b""
    return setup


FILESYSTEM: list[tuple[str, Setup]] = [
    ("default", files([])),
    ("crc-large", files([b"-a", b"crc"], large=True)),
    ("crc32b-large", files([b"-a", b"crc32b"], large=True)),
    ("bsd", files([b"-a", b"bsd"])),
    ("sysv", files([b"-a", b"sysv"])),
    ("md5", files([b"-a", b"md5"])),
    ("sha1", files([b"-a", b"sha1"])),
    ("sha256", files([b"-a", b"sha256"])),
    ("sha3", files([b"-a", b"sha3"])),
    ("blake2b", files([b"-a", b"blake2b"])),
    ("base64", files([b"-a", b"sha256", b"--base64"])),
    ("raw", files([b"-a", b"sha256", b"--raw"])),
    ("tagged", files([b"-a", b"sha256", b"--tag"])),
    ("untagged", files([b"-a", b"sha256", b"--untagged"])),
    ("length", files([b"-a", b"blake2b", b"-l", b"256"])),
    ("raw-name", files([b"-a", b"crc"], raw=True)),
    ("two-files", two_files([b"-a", b"crc"])),
    ("missing", lambda _directory: ([b"missing"], b"")),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--hybrid", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    canonical, hybrid = args.canonical.resolve(), args.hybrid.resolve()
    checked = 0
    with tempfile.TemporaryDirectory(prefix="rustbox-small-10-") as temporary:
        root = Path(temporary)
        link = root / "cksum"
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
                    if actual != expected:
                        raise AssertionError((locale, mode, name, expected, actual))
                    checked += 1

    result = {
        "schema": 1,
        "cases": checked,
        "passed": checked,
        "locales": LOCALES,
        "applets": ["cksum"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
