#!/usr/bin/env python3
"""Differential ordering, key, locale, merge, and general-numeric checks for GNU sort."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path


LOCALES = ["C", "en_US.UTF-8", "fr_FR", "tr_TR.UTF-8", "ja_JP.EUC-JP"]
DATA = b"10 ten\n2 two\n-0 zero\nnan nan\ninf infinity\n1.000000000000000001 precise\nJan month\n1K human\na10 version\na2 version\n"
CASES = [
    ([], DATA), ([b"-r"], DATA), ([b"-u"], DATA + b"2 two\n"),
    ([b"-n"], DATA), ([b"-g"], DATA), ([b"-h"], DATA),
    ([b"-V"], DATA), ([b"-M"], DATA), ([b"-f"], DATA),
    ([b"-k1,1g"], DATA), ([b"-k2,2"], DATA), ([b"-t", b":", b"-k2,2n"], b"x:10\ny:2\nz:-1\n"),
    ([b"-z"], b"z\0a\0m\0"), ([b"--stable", b"-k1,1n"], DATA),
    ([b"--parallel=2", b"-S", b"64K"], DATA * 100),
    ([b"-c", b"-n"], b"1\n2\n3\n"), ([b"-C", b"-n"], b"2\n1\n"),
    ([b"--debug", b"-g"], DATA), ([b"--help"], b""), ([b"--version"], b""),
]


def environment(locale: str, cwd: Path) -> dict[bytes, bytes]:
    env = os.environb.copy()
    for name in (b"LANG", b"LANGUAGE", b"LC_ALL", b"LC_MESSAGES", b"TZ"):
        env.pop(name, None)
    env[b"LC_ALL"] = locale.encode()
    env[b"TZ"] = b"UTC0"
    env[b"PWD"] = os.fsencode(cwd)
    return env


def run(binary: Path, link: Path, arguments: list[bytes], data: bytes,
        mode: str, locale: str, cwd: Path) -> tuple[int, bytes, bytes]:
    if mode == "explicit":
        command = [os.fsencode(binary), b"--coreutils-prog=sort", *arguments]
    else:
        link.unlink(missing_ok=True)
        link.symlink_to(binary)
        command = [os.fsencode(link), *arguments]
    process = subprocess.run(command, cwd=cwd, env=environment(locale, cwd), input=data,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    return process.returncode, process.stdout, process.stderr


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--hybrid", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    canonical, hybrid = args.canonical.resolve(), args.hybrid.resolve()
    checked = 0
    with tempfile.TemporaryDirectory(prefix="rustbox-small-23-") as temporary:
        root = Path(temporary)
        link = root / "sort"
        for locale in LOCALES:
            for mode in ("explicit", "argv0"):
                for arguments, data in CASES:
                    expected = run(canonical, link, arguments, data, mode, locale, root)
                    actual = run(hybrid, link, arguments, data, mode, locale, root)
                    if actual != expected:
                        raise AssertionError((locale, mode, arguments, expected, actual))
                    checked += 1
    result = {"schema": 1, "cases": checked, "passed": checked,
              "locales": LOCALES, "applets": ["sort"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
