#!/usr/bin/env python3
"""Differential byte-format and native-floating checks for GNU od."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path


LOCALES = ["C", "en_US.UTF-8", "fr_FR", "tr_TR.UTF-8", "ja_JP.EUC-JP"]
DATA = bytes(range(256)) + b"hello printable string\0" + bytes(range(63, -1, -1))
CASES = [
    ([], DATA), ([b"-An", b"-tx1"], DATA), ([b"-An", b"-td2"], DATA),
    ([b"-An", b"-to4z"], DATA), ([b"-An", b"-tc"], DATA),
    ([b"-An", b"-tfH"], DATA), ([b"-An", b"-tfB"], DATA),
    ([b"-An", b"-tfF"], DATA), ([b"-An", b"-tfD"], DATA),
    ([b"-An", b"-tfL"], DATA),
    ([b"-An", b"--endian=big", b"-tfH"], DATA),
    ([b"-An", b"--endian=little", b"-tfH"], DATA),
    ([b"-An", b"--endian=big", b"-tfB"], DATA),
    ([b"-An", b"--endian=little", b"-tfL"], DATA),
    ([b"-j", b"17", b"-N", b"73", b"-w24", b"-tx2"], DATA),
    ([b"-v", b"-w8"], b"\0" * 64), ([b"-S3"], DATA),
    ([b"--traditional", b"+10"], DATA), ([b"-t", b"invalid"], DATA),
    ([b"--endian=invalid"], DATA), ([b"--help"], b""), ([b"--version"], b""),
]


def environment(locale: str, cwd: Path) -> dict[bytes, bytes]:
    env = os.environb.copy()
    for name in (b"LANG", b"LANGUAGE", b"LC_ALL", b"LC_MESSAGES", b"TZ"):
        env.pop(name, None)
    env[b"LC_ALL"] = locale.encode()
    env[b"TZ"] = b"UTC0"
    env[b"PWD"] = os.fsencode(cwd)
    return env


def run(binary: Path, link: Path, arguments: list[bytes], data: bytes, mode: str, locale: str, cwd: Path) -> tuple[int, bytes, bytes]:
    if mode == "explicit":
        command = [os.fsencode(binary), b"--coreutils-prog=od", *arguments]
    else:
        link.unlink(missing_ok=True)
        link.symlink_to(binary)
        command = [os.fsencode(link), *arguments]
    process = subprocess.run(
        command, cwd=cwd, env=environment(locale, cwd), input=data,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
    )
    return process.returncode, process.stdout, process.stderr


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--hybrid", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    canonical, hybrid = args.canonical.resolve(), args.hybrid.resolve()
    checked = 0
    with tempfile.TemporaryDirectory(prefix="rustbox-small-19-") as temporary:
        root = Path(temporary)
        link = root / "od"
        for locale in LOCALES:
            for mode in ("explicit", "argv0"):
                for arguments, data in CASES:
                    expected = run(canonical, link, arguments, data, mode, locale, root)
                    actual = run(hybrid, link, arguments, data, mode, locale, root)
                    if actual != expected:
                        raise AssertionError((locale, mode, arguments, expected, actual))
                    checked += 1
    result = {"schema": 1, "cases": checked, "passed": checked, "locales": LOCALES, "applets": ["od"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
