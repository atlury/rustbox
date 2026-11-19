#!/usr/bin/env python3
"""Differential public, file-list and CPU-dispatch checks for GNU wc."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable


LOCALES = ["C", "en_US.UTF-8", "fr_FR", "tr_TR.UTF-8", "ja_JP.EUC-JP"]
INPUTS = [
    b"",
    b"one two\nthree\n",
    b"no-final-newline",
    "snowman \u2603 and caf\u00e9\n".encode(),
    b"bad-utf8-\xff word\n",
    bytes(range(256)) * 5,
]
STATELESS = [
    ([], data, None) for data in INPUTS
] + [
    ([option], b"one two\nthree\n", None)
    for option in (b"-c", b"-l", b"-w", b"-m", b"-L", b"-clw", b"-lwmLc")
] + [
    ([b"--total=always"], b"one two\n", None),
    ([b"--total=only"], b"one two\n", None),
    ([b"--total=never"], b"one two\n", None),
    ([b"--files0-from=-"], b"", None),
    ([b"--files0-from=-", b"operand"], b"", None),
    ([b"--total=invalid"], b"", None),
    ([b"--help"], b"", None),
    ([b"--version"], b"", None),
    ([b"--debug", b"-l"], b"line\n" * 20000, None),
    ([b"--debug", b"-l"], b"line\n" * 20000, "glibc.cpu.hwcaps=-AVX512F"),
    ([b"--debug", b"-l"], b"line\n" * 20000, "glibc.cpu.hwcaps=-AVX512F,-AVX2"),
]


def environment(locale: str, cwd: Path, tunable: str | None) -> dict[bytes, bytes]:
    env = os.environb.copy()
    for name in (b"LANG", b"LANGUAGE", b"LC_ALL", b"LC_MESSAGES", b"TZ", b"GLIBC_TUNABLES"):
        env.pop(name, None)
    env[b"LC_ALL"] = locale.encode()
    env[b"TZ"] = b"UTC0"
    env[b"PWD"] = os.fsencode(cwd)
    if tunable is not None:
        env[b"GLIBC_TUNABLES"] = tunable.encode()
    return env


def command(binary: Path, link: Path, arguments: list[bytes], mode: str) -> list[bytes]:
    if mode == "explicit":
        return [os.fsencode(binary), b"--coreutils-prog=wc", *arguments]
    link.unlink(missing_ok=True)
    link.symlink_to(binary)
    return [os.fsencode(link), *arguments]


def run(
    binary: Path, link: Path, arguments: list[bytes], input_bytes: bytes,
    mode: str, locale: str, cwd: Path, tunable: str | None = None,
) -> tuple[int, bytes, bytes]:
    process = subprocess.run(
        command(binary, link, arguments, mode), cwd=cwd,
        env=environment(locale, cwd, tunable), input=input_bytes,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
    )
    prefix = os.fsencode(cwd)
    return (
        process.returncode,
        process.stdout.replace(prefix, b"$CWD"),
        process.stderr.replace(prefix, b"$CWD"),
    )


Setup = Callable[[Path], tuple[list[bytes], bytes]]


def one_file(arguments: list[bytes], payload: bytes = b"one two\nthree\n", name: bytes = b"input") -> Setup:
    def setup(directory: Path) -> tuple[list[bytes], bytes]:
        path = os.path.join(os.fsencode(directory), name)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT, 0o640)
        os.write(descriptor, payload)
        os.close(descriptor)
        return [*arguments, name], b""
    return setup


def two_files(arguments: list[bytes], total: bytes | None = None) -> Setup:
    def setup(directory: Path) -> tuple[list[bytes], bytes]:
        (directory / "one").write_bytes(b"one two\n")
        (directory / "two").write_bytes(b"three\nfour five\n")
        extra = [] if total is None else [b"--total=" + total]
        return [*arguments, *extra, b"one", b"two"], b""
    return setup


def files0(stdin: bool) -> Setup:
    def setup(directory: Path) -> tuple[list[bytes], bytes]:
        (directory / "one").write_bytes(b"one\n")
        raw = b"raw-\xff"
        descriptor = os.open(os.path.join(os.fsencode(directory), raw), os.O_WRONLY | os.O_CREAT, 0o600)
        os.write(descriptor, b"two words\n")
        os.close(descriptor)
        names = b"one\0" + raw + b"\0"
        if stdin:
            return [b"--files0-from=-"], names
        (directory / "names").write_bytes(names)
        return [b"--files0-from=names"], b""
    return setup


FILESYSTEM: list[tuple[str, Setup]] = [
    ("one", one_file([])),
    ("raw-name", one_file([], name=b"raw-\xff")),
    ("newline-name", one_file([], name=b"line\nbreak")),
    ("long", one_file([b"--debug", b"-l"], b"x\n" * 300000)),
    ("bytes", one_file([b"-c"], bytes(range(256)) * 4096)),
    ("two", two_files([])),
    ("total-always", two_files([], b"always")),
    ("total-only", two_files([], b"only")),
    ("total-never", two_files([], b"never")),
    ("files0-stdin", files0(True)),
    ("files0-file", files0(False)),
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
    with tempfile.TemporaryDirectory(prefix="rustbox-small-17-") as temporary:
        root = Path(temporary)
        link = root / "wc"
        for locale in LOCALES:
            for mode in ("explicit", "argv0"):
                for arguments, input_bytes, tunable in STATELESS:
                    expected = run(canonical, link, arguments, input_bytes, mode, locale, root, tunable)
                    actual = run(hybrid, link, arguments, input_bytes, mode, locale, root, tunable)
                    if actual != expected:
                        raise AssertionError((locale, mode, arguments, tunable, expected, actual))
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

    result = {"schema": 1, "cases": checked, "passed": checked, "locales": LOCALES, "applets": ["wc"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
