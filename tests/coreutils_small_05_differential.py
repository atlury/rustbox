#!/usr/bin/env python3
"""Differential public and filesystem checks for Coreutils small batch 05."""

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
STATELESS: dict[bytes, list[tuple[list[bytes], bytes]]] = {
    b"base32": [
        ([], b""), ([], b"abc"), ([], b"\x00\xffbinary\n"),
        ([b"--wrap=4"], b"abcdef"), ([b"--wrap=0"], b"abcdef"),
        ([b"--decode"], b"MFRGG===\n"), ([b"-di"], b"M F!R G G===\n"),
        ([b"--decode"], b"invalid!"), ([b"-x"], b""),
    ],
    b"chroot": [
        ([], b""), ([b"missing-root"], b""),
        ([b"--userspec=0:0", b"missing-root", b"/bin/true"], b""),
        ([b"--skip-chdir", b"missing-root"], b""), ([b"-x"], b""),
    ],
    b"fold": [
        ([], b"alpha beta gamma\n"), ([b"-w", b"4"], b"abcdefgh\n"),
        ([b"-s", b"-w", b"6"], b"alpha beta gamma\n"),
        ([b"-b", b"-w", b"3"], bytes([0xC3, 0xA9, 0xC3, 0xA9, 0x0A])),
        ([b"-w", b"0"], b"abc\n"), ([b"-x"], b""),
    ],
    b"kill": [
        ([b"-l"], b""), ([b"-L"], b""), ([b"-l", b"9"], b""),
        ([b"-l", b"TERM"], b""), ([b"-s", b"0", b"99999999"], b""),
        ([b"-n", b"0", b"99999999"], b""), ([b"-x"], b""),
    ],
    b"paste": [
        ([], b"a\nb\n"), ([b"-s"], b"a\nb\n"),
        ([b"-d", b",;"], b"a\nb\n"), ([b"-z"], b"a\0b\0"),
        ([b"-x"], b""),
    ],
    b"sum": [
        ([], b""), ([], b"abc\n"), ([b"-s"], b"abc\n"),
        ([b"-r"], b"abc\n"), ([b"--sysv"], b"\x00\xffdata"), ([b"-x"], b""),
    ],
    b"tee": [
        ([], b""), ([], b"alpha\n"), ([b"-i"], b"alpha\n"),
        ([b"-p"], b"alpha\n"), ([b"--output-error=warn"], b"alpha\n"),
        ([b"-x"], b""),
    ],
    b"uname": [
        ([], b""), ([b"-a"], b""), ([b"-s"], b""), ([b"-n"], b""),
        ([b"-r"], b""), ([b"-m"], b""), ([b"-o"], b""), ([b"-x"], b""),
    ],
}


def environment(locale: str, cwd: Path | None = None) -> dict[bytes, bytes]:
    env = os.environb.copy()
    for name in (b"LANG", b"LANGUAGE", b"LC_ALL", b"LC_MESSAGES", b"QUOTING_STYLE"):
        env.pop(name, None)
    env[b"LC_ALL"] = locale.encode()
    if cwd is not None:
        env[b"PWD"] = os.fsencode(cwd)
    return env


def command(binary: Path, link: Path, applet: bytes, arguments: list[bytes], mode: str) -> list[bytes]:
    if mode == "explicit":
        return [os.fsencode(binary), b"--coreutils-prog=" + applet, *arguments]
    link.unlink(missing_ok=True)
    link.symlink_to(binary)
    return [os.fsencode(link), *arguments]


def normalize_output(data: bytes, cwd: Path | None) -> bytes:
    return data if cwd is None else data.replace(os.fsencode(cwd), b"$CWD")


def run(
    binary: Path, link: Path, applet: bytes, arguments: list[bytes], input_bytes: bytes,
    mode: str, locale: str, cwd: Path | None = None,
) -> tuple[int, bytes, bytes]:
    process = subprocess.run(
        command(binary, link, applet, arguments, mode),
        cwd=cwd,
        env=environment(locale, cwd),
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=15,
    )
    return (
        process.returncode,
        normalize_output(process.stdout, cwd),
        normalize_output(process.stderr, cwd),
    )


def snapshot(directory: Path, include_times: bool = False) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    root = os.fsencode(directory)
    for current, directories, files in os.walk(root):
        directories.sort()
        files.sort()
        for name in [*directories, *files]:
            path = os.path.join(current, name)
            metadata = os.lstat(path)
            record: dict[str, object] = {
                "name": os.fsdecode(os.path.relpath(path, root)).encode("unicode_escape").decode(),
                "mode": stat.S_IMODE(metadata.st_mode),
                "size": metadata.st_size,
            }
            if include_times:
                record["mtime_ns"] = metadata.st_mtime_ns
            if stat.S_ISLNK(metadata.st_mode):
                record.update(kind="symlink", target=os.fsencode(os.readlink(path)).hex())
            elif stat.S_ISREG(metadata.st_mode):
                record.update(kind="regular", data=Path(os.fsdecode(path)).read_bytes().hex())
            elif stat.S_ISDIR(metadata.st_mode):
                record["kind"] = "directory"
            records.append(record)
    return records


Setup = Callable[[Path], tuple[list[bytes], bytes]]


def plain(arguments: list[bytes], input_bytes: bytes = b"") -> Setup:
    return lambda _directory: (arguments, input_bytes)


def input_file(name: str, data: bytes, arguments: list[bytes] | None = None) -> Setup:
    def setup(directory: Path) -> tuple[list[bytes], bytes]:
        (directory / name).write_bytes(data)
        return arguments or [os.fsencode(name)], b""
    return setup


def paste_files(arguments: list[bytes]) -> Setup:
    def setup(directory: Path) -> tuple[list[bytes], bytes]:
        (directory / "left").write_bytes(b"a\nb\nc\n")
        (directory / "right").write_bytes(b"1\n2\n")
        return [*arguments, b"left", b"right"], b""
    return setup


def tee_file(arguments: list[bytes], initial: bytes | None = None) -> Setup:
    def setup(directory: Path) -> tuple[list[bytes], bytes]:
        if initial is not None:
            (directory / "out").write_bytes(initial)
        return [*arguments, b"out"], b"new\x00data\n"
    return setup


def rmdir_tree(arguments: list[bytes], nonempty: bool = False) -> Setup:
    def setup(directory: Path) -> tuple[list[bytes], bytes]:
        target = directory / "a" / "b"
        target.mkdir(parents=True)
        if nonempty:
            (target / "file").write_bytes(b"x")
        return arguments, b""
    return setup


FILESYSTEM: dict[bytes, list[tuple[str, Setup]]] = {
    b"base32": [("file", input_file("input", b"\x00data\xff"))],
    b"fold": [
        ("file", input_file("input", b"alpha beta gamma\n", [b"-s", b"-w", b"7", b"input"])),
        ("missing", plain([b"missing"])),
    ],
    b"paste": [
        ("parallel", paste_files([])), ("serial", paste_files([b"-s"])),
        ("delimiter", paste_files([b"-d", b",;"])), ("missing", plain([b"missing"])),
    ],
    b"rmdir": [
        ("empty", rmdir_tree([b"a/b"])),
        ("parents", rmdir_tree([b"-p", b"a/b"])),
        ("verbose", rmdir_tree([b"-v", b"a/b"])),
        ("nonempty", rmdir_tree([b"--ignore-fail-on-non-empty", b"a/b"], True)),
        ("missing", plain([b"missing"])),
    ],
    b"sum": [
        ("file", input_file("input", b"some bytes\n")),
        ("sysv", input_file("input", b"some bytes\n", [b"-s", b"input"])),
        ("missing", plain([b"missing"])),
    ],
    b"tee": [
        ("create", tee_file([])), ("append", tee_file([b"-a"], b"old\n")),
        ("two", lambda d: ([b"one", b"two"], b"both\n")),
    ],
    b"touch": [
        ("create", plain([b"-t", b"200001020304.05", b"new"])),
        ("multiple", plain([b"-t", b"200001020304.05", b"one", b"two"])),
        ("no-create", plain([b"-c", b"-t", b"200001020304.05", b"missing"])),
    ],
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--hybrid", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    canonical, hybrid = args.canonical.resolve(), args.hybrid.resolve()
    checked = 0
    with tempfile.TemporaryDirectory(prefix="rustbox-small-05-") as temporary:
        root = Path(temporary)
        links = root / "invoke"
        links.mkdir()

        def link(applet: bytes) -> Path:
            return links / os.fsdecode(applet)

        for applet, cases in STATELESS.items():
            for locale in LOCALES:
                for mode in ("explicit", "argv0"):
                    for arguments, input_bytes in [*cases, *[(item, b"") for item in OPTIONS]]:
                        expected = run(canonical, link(applet), applet, arguments, input_bytes, mode, locale)
                        actual = run(hybrid, link(applet), applet, arguments, input_bytes, mode, locale)
                        if actual != expected:
                            raise AssertionError((applet, locale, mode, arguments, expected, actual))
                        checked += 1

        for applet, cases in FILESYSTEM.items():
            for locale in LOCALES:
                for mode in ("explicit", "argv0"):
                    for arguments in OPTIONS:
                        expected = run(canonical, link(applet), applet, arguments, b"", mode, locale)
                        actual = run(hybrid, link(applet), applet, arguments, b"", mode, locale)
                        if actual != expected:
                            raise AssertionError((applet, locale, mode, arguments, expected, actual))
                        checked += 1
                    for name, setup in cases:
                        pair = root / f"case-{checked}"
                        expected_dir, actual_dir = pair / "canonical", pair / "hybrid"
                        expected_dir.mkdir(parents=True)
                        actual_dir.mkdir()
                        expected_args, expected_input = setup(expected_dir)
                        actual_args, actual_input = setup(actual_dir)
                        expected = run(canonical, link(applet), applet, expected_args, expected_input, mode, locale, expected_dir)
                        actual = run(hybrid, link(applet), applet, actual_args, actual_input, mode, locale, actual_dir)
                        include_times = applet == b"touch" and name != "no-create"
                        expected_tree = snapshot(expected_dir, include_times)
                        actual_tree = snapshot(actual_dir, include_times)
                        if actual != expected or actual_tree != expected_tree:
                            raise AssertionError((applet, locale, mode, name, expected, actual, expected_tree, actual_tree))
                        checked += 1

    applets = [b"base32", b"chroot", b"fold", b"kill", b"paste", b"rmdir", b"sum", b"tee", b"touch", b"uname"]
    result = {
        "schema": 1,
        "cases": checked,
        "passed": checked,
        "locales": LOCALES,
        "applets": [os.fsdecode(item) for item in applets],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
