#!/usr/bin/env python3
"""Differential public and multiprecision checks for GNU factor."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path


LOCALES = ["C", "en_US.UTF-8", "fr_FR", "tr_TR.UTF-8", "ja_JP.EUC-JP"]
NUMBERS = [
    b"0", b"1", b"2", b"3", b"4", b"6", b"12", b"97", b"120",
    b"65535", b"4294967295", b"18446744073709551615",
    b"18446744073709551557", b"340282366920938463463374607431768211455",
    b"170141183460469231731687303715884105727",
]
CASES = [([number], b"") for number in NUMBERS] + [
    ([b"-h", b"120"], b""),
    ([b"-h", b"65536"], b""),
    ([b"2", b"3", b"120", b"4294967295"], b""),
    ([b"--", b"-1"], b""),
    ([b"invalid"], b""),
    ([b"12x"], b""),
    ([b"--help"], b""),
    ([b"--version"], b""),
    ([], b"2\n3 120\t4294967295\n"),
    ([b"-h"], b"64\n81\n125\n"),
    ([], b"invalid\n12\n"),
]


def environment(locale: str, cwd: Path) -> dict[bytes, bytes]:
    env = os.environb.copy()
    for name in (b"LANG", b"LANGUAGE", b"LC_ALL", b"LC_MESSAGES", b"TZ"):
        env.pop(name, None)
    env[b"LC_ALL"] = locale.encode()
    env[b"TZ"] = b"UTC0"
    env[b"PWD"] = os.fsencode(cwd)
    return env


def command(binary: Path, link: Path, arguments: list[bytes], mode: str) -> list[bytes]:
    if mode == "explicit":
        return [os.fsencode(binary), b"--coreutils-prog=factor", *arguments]
    link.unlink(missing_ok=True)
    link.symlink_to(binary)
    return [os.fsencode(link), *arguments]


def run(
    binary: Path, link: Path, arguments: list[bytes], input_bytes: bytes,
    mode: str, locale: str, cwd: Path,
) -> tuple[int, bytes, bytes]:
    process = subprocess.run(
        command(binary, link, arguments, mode), cwd=cwd,
        env=environment(locale, cwd), input=input_bytes,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
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
    with tempfile.TemporaryDirectory(prefix="rustbox-small-18-") as temporary:
        root = Path(temporary)
        link = root / "factor"
        for locale in LOCALES:
            for mode in ("explicit", "argv0"):
                for arguments, input_bytes in CASES:
                    expected = run(canonical, link, arguments, input_bytes, mode, locale, root)
                    actual = run(hybrid, link, arguments, input_bytes, mode, locale, root)
                    if actual != expected:
                        raise AssertionError((locale, mode, arguments, expected, actual))
                    checked += 1

    result = {"schema": 1, "cases": checked, "passed": checked, "locales": LOCALES, "applets": ["factor"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
