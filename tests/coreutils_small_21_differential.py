#!/usr/bin/env python3
"""Differential integer, long-double, locale, and formatting checks for GNU seq."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path


LOCALES = ["C", "en_US.UTF-8", "fr_FR", "tr_TR.UTF-8", "ja_JP.EUC-JP"]
CASES = [
    [b"5"], [b"-3", b"3"], [b"1", b"2", b"9"],
    [b"0000000000000000000000000001", b"0000000000000000000000000005"],
    [b"0", b"0.000001", b"0.000003"],
    [b"1.000000000000000001", b"0.000000000000000001", b"1.000000000000000005"],
    [b"-w", b"8", b"12"], [b"-s", b",", b"1", b"4"],
    [b"-f", b"prefix:%020.12g:suffix", b"1.25", b"0.5", b"3.25"],
    [b"1e1", b"2e1", b"9e1"], [b"0x1p0", b"0x1p-2", b"0x2p0"],
    [b"nan"], [b"1", b"0", b"2"], [b"1x", b"2"],
    [b"--help"], [b"--version"],
]


def environment(locale: str, cwd: Path) -> dict[bytes, bytes]:
    env = os.environb.copy()
    for name in (b"LANG", b"LANGUAGE", b"LC_ALL", b"LC_MESSAGES", b"TZ"):
        env.pop(name, None)
    env[b"LC_ALL"] = locale.encode()
    env[b"TZ"] = b"UTC0"
    env[b"PWD"] = os.fsencode(cwd)
    return env


def run(binary: Path, link: Path, arguments: list[bytes], mode: str,
        locale: str, cwd: Path) -> tuple[int, bytes, bytes]:
    if mode == "explicit":
        command = [os.fsencode(binary), b"--coreutils-prog=seq", *arguments]
    else:
        link.unlink(missing_ok=True)
        link.symlink_to(binary)
        command = [os.fsencode(link), *arguments]
    process = subprocess.run(
        command, cwd=cwd, env=environment(locale, cwd),
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
    with tempfile.TemporaryDirectory(prefix="rustbox-small-21-") as temporary:
        root = Path(temporary)
        link = root / "seq"
        for locale in LOCALES:
            for mode in ("explicit", "argv0"):
                for arguments in CASES:
                    expected = run(canonical, link, arguments, mode, locale, root)
                    actual = run(hybrid, link, arguments, mode, locale, root)
                    if actual != expected:
                        raise AssertionError((locale, mode, arguments, expected, actual))
                    checked += 1
    result = {"schema": 1, "cases": checked, "passed": checked,
              "locales": LOCALES, "applets": ["seq"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
