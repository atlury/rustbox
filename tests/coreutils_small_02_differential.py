#!/usr/bin/env python3
"""Differential public, timing, and filesystem checks for small batch 02."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Callable


LOCALES = ["C", "en_US.UTF-8", "fr_FR", "tr_TR.UTF-8", "ja_JP.EUC-JP"]
OPTIONS = [[b"--help"], [b"--version"]]
STATELESS: dict[bytes, list[list[bytes]]] = {
    b"arch": [[], [b"extra"], [b"-x"]],
    b"echo": [
        [], [b"hello"], [b"alpha", b"beta gamma"], [b"-n", b"no newline"],
        [b"-e", br"a\tb\n"], [b"-E", br"a\tb"], [b"-ne", br"\x41\101"],
        [b"--", b"value"], [b"-x"], [b"\xff", b"\xfe"],
    ],
    b"hostname": [[], [b"extra"], [b"-x"]],
    b"nice": [
        [], [b"-n", b"0"], [b"-n", b"1", b"/bin/sh", b"-c", b"printf nice"],
        [b"--adjustment=2", b"/bin/sh", b"-c", b"exit 7"],
        [b"missing-rustbox-command"], [b"-n", b"bad"], [b"-x"],
    ],
    b"nproc": [[], [b"--all"], [b"--ignore=0"], [b"--ignore=1"], [b"-x"]],
    b"sleep": [[], [b"0"], [b"0s"], [b"0.001"], [b"0", b"0"], [b"bad"], [b"-x"]],
}


def environment(locale: str) -> dict[bytes, bytes]:
    env = os.environb.copy()
    for name in (b"LANG", b"LANGUAGE", b"LC_ALL", b"LC_MESSAGES", b"QUOTING_STYLE"):
        env.pop(name, None)
    env[b"LC_ALL"] = locale.encode()
    return env


def command(binary: Path, link: Path, applet: bytes, arguments: list[bytes], mode: str) -> list[bytes]:
    if mode == "explicit":
        return [os.fsencode(binary), b"--coreutils-prog=" + applet, *arguments]
    link.unlink(missing_ok=True)
    link.symlink_to(binary)
    return [os.fsencode(link), *arguments]


def run(
    binary: Path,
    link: Path,
    applet: bytes,
    arguments: list[bytes],
    mode: str,
    locale: str,
    cwd: Path | None = None,
) -> tuple[int, bytes, bytes]:
    process = subprocess.run(
        command(binary, link, applet, arguments, mode),
        cwd=cwd,
        env=environment(locale),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )
    stdout = process.stdout
    stderr = process.stderr
    if applet == b"uptime":
        stdout = re.sub(rb"[0-9]+(?:[.,][0-9]+)?", b"#", stdout)
    if cwd is not None:
        encoded = os.fsencode(cwd)
        stdout = stdout.replace(encoded, b"$CWD")
        stderr = stderr.replace(encoded, b"$CWD")
    return process.returncode, stdout, stderr


def snapshot(directory: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    root = os.fsencode(directory)
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        metadata = os.lstat(path)
        record: dict[str, object] = {
            "name": name.hex(),
            "mode": stat.S_IMODE(metadata.st_mode),
        }
        if stat.S_ISLNK(metadata.st_mode):
            record.update(kind="symlink", target=os.fsencode(os.readlink(path)).hex())
        elif stat.S_ISREG(metadata.st_mode):
            record.update(kind="regular", data=Path(os.fsdecode(path)).read_bytes().hex())
        elif stat.S_ISDIR(metadata.st_mode):
            record["kind"] = "directory"
        else:
            record["kind"] = "other"
        records.append(record)
    return records


Setup = Callable[[Path], list[bytes]]


def plain(arguments: list[bytes]) -> Setup:
    return lambda _directory: arguments


def readlink_regular(directory: Path) -> list[bytes]:
    (directory / "target").write_bytes(b"data")
    (directory / "link").symlink_to("target")
    return [b"link"]


def readlink_chain(directory: Path) -> list[bytes]:
    (directory / "dir").mkdir()
    (directory / "dir" / "target").write_bytes(b"data")
    (directory / "second").symlink_to("dir/target")
    (directory / "first").symlink_to("second")
    return [b"-f", b"first"]


def readlink_missing(directory: Path) -> list[bytes]:
    (directory / "prefix").mkdir()
    return [b"-m", b"prefix/missing/../leaf"]


def readlink_raw(directory: Path) -> list[bytes]:
    target = os.path.join(os.fsencode(directory), b"\xfe")
    descriptor = os.open(target, os.O_CREAT | os.O_WRONLY, 0o600)
    os.close(descriptor)
    os.symlink(b"\xfe", os.path.join(os.fsencode(directory), b"\xff"))
    return [b"\xff"]


def sync_file(directory: Path) -> list[bytes]:
    (directory / "payload").write_bytes(b"payload")
    return [b"payload"]


def sync_filesystem(directory: Path) -> list[bytes]:
    (directory / "payload").write_bytes(b"payload")
    return [b"--file-system", b"payload"]


def empty_utmp(directory: Path) -> list[bytes]:
    (directory / "empty-utmp").write_bytes(b"")
    return [b"empty-utmp"]


FILESYSTEM: dict[bytes, list[tuple[str, Setup]]] = {
    b"readlink": [
        ("none", plain([])), ("missing", plain([b"missing"])),
        ("regular", readlink_regular), ("chain", readlink_chain),
        ("missing-canonical", readlink_missing), ("raw", readlink_raw),
    ],
    b"sync": [
        ("all", plain([])), ("missing", plain([b"missing"])),
        ("file", sync_file), ("filesystem", sync_filesystem),
    ],
    b"uptime": [
        ("empty", empty_utmp), ("missing", plain([b"missing-utmp"])),
        ("extra", plain([b"one", b"two"])),
    ],
    b"users": [
        ("empty", empty_utmp), ("missing", plain([b"missing-utmp"])),
        ("extra", plain([b"one", b"two"])),
    ],
}


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
    with tempfile.TemporaryDirectory(prefix="rustbox-small-02-") as temporary:
        root = Path(temporary)
        links = root / "invoke"
        links.mkdir()

        def link(applet: bytes) -> Path:
            return links / os.fsdecode(applet)

        for applet, cases in STATELESS.items():
            for locale in LOCALES:
                for mode in ("explicit", "argv0"):
                    for arguments in [*cases, *OPTIONS]:
                        expected = run(canonical, link(applet), applet, arguments, mode, locale)
                        actual = run(hybrid, link(applet), applet, arguments, mode, locale)
                        if actual != expected:
                            raise AssertionError((applet, locale, mode, arguments, expected, actual))
                        checked += 1

        for applet, cases in FILESYSTEM.items():
            for locale in LOCALES:
                for mode in ("explicit", "argv0"):
                    for arguments in OPTIONS:
                        expected = run(canonical, link(applet), applet, arguments, mode, locale)
                        actual = run(hybrid, link(applet), applet, arguments, mode, locale)
                        if actual != expected:
                            raise AssertionError((applet, locale, mode, arguments, expected, actual))
                        checked += 1
                    for case_name, setup in cases:
                        pair = root / f"case-{checked}"
                        expected_dir = pair / "canonical"
                        actual_dir = pair / "hybrid"
                        expected_dir.mkdir(parents=True)
                        actual_dir.mkdir()
                        expected_args = setup(expected_dir)
                        actual_args = setup(actual_dir)
                        expected = run(
                            canonical, link(applet), applet, expected_args, mode, locale, expected_dir
                        )
                        actual = run(
                            hybrid, link(applet), applet, actual_args, mode, locale, actual_dir
                        )
                        if actual != expected or snapshot(actual_dir) != snapshot(expected_dir):
                            raise AssertionError(
                                (applet, locale, mode, case_name, expected, actual,
                                 snapshot(expected_dir), snapshot(actual_dir))
                            )
                        checked += 1

    result = {
        "schema": 1,
        "cases": checked,
        "passed": checked,
        "locales": LOCALES,
        "applets": [os.fsdecode(item) for item in [*STATELESS, *FILESYSTEM]],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
