#!/usr/bin/env python3
"""Differential formatting, diagnostics, and native-long-double checks for GNU printf."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path


LOCALES = ["C", "en_US.UTF-8", "fr_FR", "tr_TR.UTF-8", "ja_JP.EUC-JP"]
CASES = [
    ([b"%s:%d:%u:%x\\n", b"text", b"-12", b"34", b"255"], None),
    ([b"%f|%.18Lg|%La\\n", b"1.25", b"3.1415926535897932384626", b"0x1.8p+2"], None),
    ([b"%*.*Lf\\n", b"24", b"12", b"1.234567890123456789"], None),
    ([b"%2$.*1$Lf\\n", b"9", b"2.718281828459045235"], None),
    ([b"%La %LE %LG\\n", b"inf", b"-nan", b"-0"], None),
    ([b"%Lf\\n", b"12.5tail"], None),
    ([b"%Lf\\n", b"not-a-number"], None),
    ([b"%Lf %Lf\\n", b"'A", b'"Z'], None),
    ([b"%Lf\\n", "'é".encode()], None),
    ([b"%b", b"left\\nright\\tend"], None),
    ([b"%q\\n", b"a b'c\\nd"], None),
    ([b"%d\\n", b"'AB"], None),
    ([b"%d\\n", b"'AB"], b"1"),
    ([b"%999999999999999999999f", b"1"], None),
    ([b"--help"], None),
    ([b"--version"], None),
]


def environment(locale: str, cwd: Path, posix: bytes | None) -> dict[bytes, bytes]:
    env = os.environb.copy()
    for name in (b"LANG", b"LANGUAGE", b"LC_ALL", b"LC_MESSAGES", b"TZ", b"POSIXLY_CORRECT"):
        env.pop(name, None)
    env[b"LC_ALL"] = locale.encode()
    env[b"TZ"] = b"UTC0"
    env[b"PWD"] = os.fsencode(cwd)
    if posix is not None:
        env[b"POSIXLY_CORRECT"] = posix
    return env


def run(binary: Path, link: Path, arguments: list[bytes], mode: str,
        locale: str, posix: bytes | None, cwd: Path) -> tuple[int, bytes, bytes]:
    if mode == "explicit":
        command = [os.fsencode(binary), b"--coreutils-prog=printf", *arguments]
    else:
        link.unlink(missing_ok=True)
        link.symlink_to(binary)
        command = [os.fsencode(link), *arguments]
    process = subprocess.run(
        command, cwd=cwd, env=environment(locale, cwd, posix),
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
    with tempfile.TemporaryDirectory(prefix="rustbox-small-20-") as temporary:
        root = Path(temporary)
        link = root / "printf"
        for locale in LOCALES:
            for mode in ("explicit", "argv0"):
                for arguments, posix in CASES:
                    expected = run(canonical, link, arguments, mode, locale, posix, root)
                    actual = run(hybrid, link, arguments, mode, locale, posix, root)
                    if actual != expected:
                        raise AssertionError((locale, mode, arguments, posix, expected, actual))
                    checked += 1
    result = {"schema": 1, "cases": checked, "passed": checked,
              "locales": LOCALES, "applets": ["printf"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
