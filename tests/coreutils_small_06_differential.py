#!/usr/bin/env python3
"""Differential public and filesystem checks for Coreutils small batch 06."""

from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Callable


LOCALES = ["C", "en_US.UTF-8", "fr_FR", "tr_TR.UTF-8", "ja_JP.EUC-JP"]
OPTIONS = [[b"--help"], [b"--version"]]
STATELESS: dict[bytes, list[tuple[list[bytes], bytes]]] = {
    b"cat": [
        ([], b""), ([], b"alpha\nbeta\n"), ([], b"\x00\xffbinary\n"),
        ([b"-n"], b"a\nb\n"), ([b"-b"], b"a\n\nb\n"),
        ([b"-s"], b"a\n\n\n\nb\n"), ([b"-A"], b"a\t\x00\n"),
        ([b"-x"], b""),
    ],
    b"dircolors": [
        ([b"-b"], b""), ([b"-c"], b""), ([b"-p"], b""),
        ([b"-b", b"-"], b"TERM xterm\nDIR 01;34\nLINK target\n"),
        ([b"-c", b"-"], b"TERM xterm\nFILE 00\n"), ([b"-x"], b""),
    ],
    b"fmt": [
        ([], b"alpha beta gamma delta\n"), ([b"-w", b"8"], b"alpha beta gamma\n"),
        ([b"-c", b"-w", b"12"], b"  alpha beta\n    gamma delta\n"),
        ([b"-t", b"-w", b"12"], b"* alpha beta\n  gamma delta\n"),
        ([b"-s"], b"alpha beta gamma\n"), ([b"-u"], b"a.  b. c\n"),
        ([b"-g", b"4", b"-w", b"10"], b"alpha beta gamma\n"), ([b"-x"], b""),
    ],
    b"nl": [
        ([], b"a\nb\n"), ([b"-ba"], b"a\n\nb\n"),
        ([b"-bt"], b"a\n\nb\n"), ([b"-nrz", b"-w3", b"-s:"], b"a\nb\n"),
        ([b"-v", b"7", b"-i", b"3"], b"a\nb\n"),
        ([], b"\\:\nheader\n\\:\nbody\n"), ([b"-x"], b""),
    ],
    b"pinky": [
        ([], b""), ([b"-s"], b""), ([b"-l", b"rustbox-no-such-user"], b""),
        ([b"rustbox-no-such-user"], b""), ([b"-x"], b""),
    ],
    b"realpath": [
        ([b"missing"], b""), ([b"-e", b"missing"], b""),
        ([b"-m", b"missing/../path"], b""), ([b"--relative-to=. ", b"."], b""),
        ([b"-x"], b""),
    ],
    b"shuf": [
        ([b"-e"], b""), ([b"-i", b"1-0"], b""),
        ([b"-i", b"bad"], b""), ([b"-n", b"-1"], b""), ([b"-x"], b""),
    ],
    b"tac": [
        ([], b""), ([], b"a\nb\nc\n"), ([], b"a\nb\nc"),
        ([b"-s", b":"], b"a:b:c:"), ([b"-r", b"-s", b"[0-9]+"], b"a1b22c333"),
        ([b"-b", b"-s", b":"], b"a:b:c:"), ([b"-x"], b""),
    ],
    b"timeout": [
        ([b"0", b"/bin/true"], b""), ([b"0", b"/bin/false"], b""),
        ([b"1s", b"/bin/true"], b""),
        ([b"--preserve-status", b"0", b"/bin/false"], b""),
        ([b"--signal=TERM", b"0", b"/bin/true"], b""),
        ([b"0.01", b"/bin/sh", b"-c", b"sleep 1"], b""),
        ([b"bad", b"/bin/true"], b""), ([], b""), ([b"-x"], b""),
    ],
    b"uniq": [
        ([], b""), ([], b"a\na\nb\nb\nb\nc\n"),
        ([b"-c"], b"a\na\nb\nb\nb\nc\n"), ([b"-d"], b"a\na\nb\nb\nb\nc\n"),
        ([b"-u"], b"a\na\nb\nb\nb\nc\n"), ([b"-D"], b"a\na\nb\nb\nb\nc\n"),
        ([b"-i"], b"A\na\nB\nb\n"), ([b"-f", b"1"], b"x a\ny a\nz b\n"),
        ([b"-s", b"2"], b"xxa\nyya\nzzb\n"), ([b"-w", b"2"], b"abc\nabz\nxy\n"),
        ([b"-z"], b"a\0a\0b\0"), ([b"--group=prepend"], b"a\na\nb\n"),
        ([b"-x"], b""),
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
        command(binary, link, applet, arguments, mode), cwd=cwd,
        env=environment(locale, cwd), input=input_bytes,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20,
    )
    return (
        process.returncode,
        normalize_output(process.stdout, cwd),
        normalize_output(process.stderr, cwd),
    )


def snapshot(directory: Path) -> list[dict[str, object]]:
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
                "mode": stat.S_IMODE(metadata.st_mode), "size": metadata.st_size,
            }
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


def multiple_files(arguments: list[bytes]) -> Setup:
    def setup(directory: Path) -> tuple[list[bytes], bytes]:
        (directory / "one").write_bytes(b"alpha\nbeta\n")
        (directory / "two").write_bytes(b"gamma\ndelta\n")
        return [*arguments, b"one", b"two"], b""
    return setup


def realpath_tree(arguments: list[bytes]) -> Setup:
    def setup(directory: Path) -> tuple[list[bytes], bytes]:
        (directory / "a" / "b").mkdir(parents=True)
        (directory / "a" / "b" / "file").write_bytes(b"data")
        (directory / "link").symlink_to("a/b")
        return arguments, b""
    return setup


def shuf_source(arguments: list[bytes], input_bytes: bytes = b"") -> Setup:
    def setup(directory: Path) -> tuple[list[bytes], bytes]:
        (directory / "random").write_bytes(bytes(range(256)) * 256)
        return [b"--random-source=random", *arguments], input_bytes
    return setup


def uniq_output(arguments: list[bytes]) -> Setup:
    def setup(directory: Path) -> tuple[list[bytes], bytes]:
        (directory / "input").write_bytes(b"a\na\nb\nb\nb\nc\n")
        return [*arguments, b"input", b"output"], b""
    return setup


def uniq_zero_output(directory: Path) -> tuple[list[bytes], bytes]:
    (directory / "input").write_bytes(b"a\0a\0b\0")
    return [b"-z", b"input", b"output"], b""


FILESYSTEM: dict[bytes, list[tuple[str, Setup]]] = {
    b"cat": [
        ("file", input_file("input", b"a\n\nb\n", [b"-n", b"input"])),
        ("multiple", multiple_files([b"-s"])), ("missing", plain([b"missing"])),
    ],
    b"dircolors": [
        ("config", input_file("config", b"TERM xterm\nDIR 01;34\nLINK target\n", [b"-b", b"config"])),
        ("missing", plain([b"missing"])),
    ],
    b"fmt": [
        ("file", input_file("input", b"alpha beta gamma delta epsilon\n", [b"-w", b"12", b"input"])),
        ("multiple", multiple_files([b"-w", b"10"])), ("missing", plain([b"missing"])),
    ],
    b"nl": [
        ("file", input_file("input", b"a\n\nb\n", [b"-ba", b"input"])),
        ("multiple", multiple_files([b"-nrz", b"-w3"])), ("missing", plain([b"missing"])),
    ],
    b"realpath": [
        ("physical", realpath_tree([b"-e", b"link/file"])),
        ("logical", realpath_tree([b"-L", b"link/../b/file"])),
        ("relative", realpath_tree([b"--relative-to=a", b"a/b/file"])),
        ("relative-base", realpath_tree([b"--relative-base=a", b"a/b/file"])),
        ("zero", realpath_tree([b"-z", b"a/b/file", b"link/file"])),
    ],
    b"shuf": [
        ("stdin", shuf_source([b"-n", b"3"], b"a\nb\nc\nd\ne\n")),
        ("echo", shuf_source([b"-e", b"a", b"b", b"c", b"d"])),
        ("range", shuf_source([b"-i", b"10-30", b"-n", b"7"])),
        ("repeat", shuf_source([b"-r", b"-n", b"8", b"-e", b"a", b"b", b"c"])),
    ],
    b"tac": [
        ("file", input_file("input", b"a\nb\nc\n")),
        ("separator", input_file("input", b"a:b:c:", [b"-s", b":", b"input"])),
        ("multiple", multiple_files([])), ("missing", plain([b"missing"])),
    ],
    b"uniq": [
        ("file", input_file("input", b"a\na\nb\nb\nb\nc\n")),
        ("count-output", uniq_output([b"-c"])),
        ("zero-output", uniq_zero_output),
        ("missing", plain([b"missing"])),
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
    with tempfile.TemporaryDirectory(prefix="rustbox-small-06-") as temporary:
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
                        expected_tree, actual_tree = snapshot(expected_dir), snapshot(actual_dir)
                        if actual != expected or actual_tree != expected_tree:
                            raise AssertionError((applet, locale, mode, name, expected, actual, expected_tree, actual_tree))
                        checked += 1

    applets = [b"cat", b"dircolors", b"fmt", b"nl", b"pinky", b"realpath", b"shuf", b"tac", b"timeout", b"uniq"]
    result = {
        "schema": 1, "cases": checked, "passed": checked, "locales": LOCALES,
        "applets": [os.fsdecode(item) for item in applets],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
