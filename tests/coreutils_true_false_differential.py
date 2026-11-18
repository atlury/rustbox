#!/usr/bin/env python3
"""Differential public-interface checks for canonical and hybrid true/false."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path


ARGUMENTS = [
    [],
    [b"ignored"],
    [b"--help"],
    [b"--version"],
    [b"--help", b"extra"],
    [b"--version", b"extra"],
    [b"-x"],
    [b""],
    [b"\xff"],
]
LOCALES = ["C", "en_US.UTF-8", "fr_FR", "tr_TR.UTF-8", "ja_JP.EUC-JP"]


def environment(locale: str) -> dict[bytes, bytes]:
    env = os.environb.copy()
    for name in (b"LANG", b"LANGUAGE", b"LC_ALL", b"LC_MESSAGES"):
        env.pop(name, None)
    env[b"LC_ALL"] = locale.encode()
    return env


def run(command: list[bytes], locale: str) -> tuple[int, bytes, bytes]:
    process = subprocess.run(command, env=environment(locale), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return process.returncode, process.stdout, process.stderr


def broken_output(command: list[bytes], locale: str) -> tuple[int, bytes]:
    reader, writer = os.pipe()
    os.close(reader)
    try:
        process = subprocess.Popen(
            command,
            env=environment(locale),
            stdout=writer,
            stderr=subprocess.PIPE,
        )
    finally:
        os.close(writer)
    stderr = process.communicate()[1]
    return process.returncode, stderr


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--hybrid", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    canonical = args.canonical.resolve()
    hybrid = args.hybrid.resolve()
    if not canonical.is_file() or not hybrid.is_file():
        raise RuntimeError("canonical or hybrid multicall binary is missing")

    checked = 0
    with tempfile.TemporaryDirectory(prefix="rustbox-true-false-") as temporary:
        temporary_path = Path(temporary)
        directory = temporary_path / "invoke"
        directory.mkdir()
        links = {applet: directory / applet.decode() for applet in (b"true", b"false")}

        def run_argv0(binary: Path, applet: bytes, arguments: list[bytes], locale: str) -> tuple[int, bytes, bytes]:
            link = links[applet]
            link.unlink(missing_ok=True)
            link.symlink_to(binary)
            return run([os.fsencode(link), *arguments], locale)

        for applet in (b"true", b"false"):
            for locale in LOCALES:
                for arguments in ARGUMENTS:
                    commands = {
                        "canonical-explicit": [os.fsencode(canonical), b"--coreutils-prog=" + applet, *arguments],
                        "hybrid-explicit": [os.fsencode(hybrid), b"--coreutils-prog=" + applet, *arguments],
                    }
                    explicit = run(commands["canonical-explicit"], locale)
                    argv0 = run_argv0(canonical, applet, arguments, locale)
                    if run(commands["hybrid-explicit"], locale) != explicit:
                        raise AssertionError((applet, locale, arguments, "explicit"))
                    if run_argv0(hybrid, applet, arguments, locale) != argv0:
                        raise AssertionError((applet, locale, arguments, "argv0"))
                    checked += 2

                for option in (b"--help", b"--version"):
                    expected = broken_output(
                        [os.fsencode(canonical), b"--coreutils-prog=" + applet, option], locale
                    )
                    actual = broken_output(
                        [os.fsencode(hybrid), b"--coreutils-prog=" + applet, option], locale
                    )
                    if actual != expected:
                        raise AssertionError((applet, locale, option, "broken-output"))
                    checked += 1

    result = {"schema": 1, "cases": checked, "passed": checked, "locales": LOCALES}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
