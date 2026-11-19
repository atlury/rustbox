#!/usr/bin/env python3
"""Differential scaling, rounding, locale, field, and diagnostics checks for GNU numfmt."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path


LOCALES = ["C", "en_US.UTF-8", "fr_FR", "tr_TR.UTF-8", "ja_JP.EUC-JP"]
CASES = [
    ([b"1000"], b""), ([b"--to=si", b"1000", b"999999", b"1000000"], b""),
    ([b"--to=iec-i", b"1024", b"1048576"], b""),
    ([b"--from=auto", b"1K", b"1Ki", b"2M"], b""),
    ([b"--from=si", b"--to=iec", b"1G"], b""),
    ([b"--round=nearest", b"--to=si", b"1499", b"1500"], b""),
    ([b"--round=down", b"--to=si", b"-1999"], b""),
    ([b"--format=prefix:%010.2f:suffix", b"1234.567"], b""),
    ([b"--padding=-12", b"--to=si", b"12345"], b""),
    ([b"--grouping", b"1234567.89"], b""),
    ([b"--field=2", b"--to=si"], b"left 1000 right\nother 2000000 end\n"),
    ([b"--delimiter=,", b"--field=2", b"--to=si"], b"left,1000,right\n"),
    ([b"--suffix=B", b"--to=si", b"1000B", b"invalid"], b""),
    ([b"--invalid=warn", b"--to=si", b"invalid", b"1000"], b""),
    ([b"--debug", b"--to=si", b"999500"], b""),
    ([b"--help"], b""), ([b"--version"], b""),
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
        command = [os.fsencode(binary), b"--coreutils-prog=numfmt", *arguments]
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
    with tempfile.TemporaryDirectory(prefix="rustbox-small-22-") as temporary:
        root = Path(temporary)
        link = root / "numfmt"
        for locale in LOCALES:
            for mode in ("explicit", "argv0"):
                for arguments, data in CASES:
                    expected = run(canonical, link, arguments, data, mode, locale, root)
                    actual = run(hybrid, link, arguments, data, mode, locale, root)
                    if actual != expected:
                        raise AssertionError((locale, mode, arguments, expected, actual))
                    checked += 1
    result = {"schema": 1, "cases": checked, "passed": checked,
              "locales": LOCALES, "applets": ["numfmt"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
