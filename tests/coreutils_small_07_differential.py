#!/usr/bin/env python3
"""Differential public and filesystem checks for Coreutils small batch 07."""

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
    b"expand": [
        ([], b"a\tb\n"), ([b"-t", b"4"], b"a\tb\n"),
        ([b"-i"], b"a\tb\n\tc\n"), ([b"-t", b"2,6"], b"\ta\tb\n"),
        ([b"-t", b"+4"], b"a\tb\n"), ([b"-t", b"/4"], b"a\tb\n"),
        ([], b"\x00\xff\tbytes\n"), ([b"-x"], b""),
    ],
    b"expr": [
        ([b"1", b"+", b"2"], b""), ([b"7", b"-", b"9"], b""),
        ([b"6", b"*", b"7"], b""), ([b"8", b"/", b"2"], b""),
        ([b"8", b"%", b"3"], b""), ([b"a", b"=", b"a"], b""),
        ([b"a", b"<", b"b"], b""), ([b"length", b"alpha"], b""),
        ([b"substr", b"abcdef", b"2", b"3"], b""),
        ([b"index", b"abcdef", b"dx"], b""),
        ([b"match", b"abc123", b"[a-z]*"], b""),
        ([b"abc123", b":", b"[a-z]*\\([0-9]*\\)"], b""),
        ([b"1", b"/", b"0"], b""), ([b"-x"], b""),
    ],
    b"head": [
        ([], b"a\nb\nc\nd\n"), ([b"-n", b"2"], b"a\nb\nc\n"),
        ([b"-n", b"-2"], b"a\nb\nc\nd\n"),
        ([b"-n", b"+2"], b"a\nb\nc\nd\n"),
        ([b"-c", b"3"], b"abcdef"), ([b"-c", b"-2"], b"abcdef"),
        ([b"-z", b"-n", b"2"], b"a\0b\0c\0"),
        ([b"-q"], b"a\n"), ([b"-x"], b""),
    ],
    b"test": [
        ([], b""), ([b""], b""), ([b"x"], b""), ([b"!", b""], b""),
        ([b"1", b"-eq", b"1"], b""), ([b"1", b"-lt", b"2"], b""),
        ([b"a", b"=", b"a"], b""), ([b"a", b"!=", b"b"], b""),
        ([b"(", b"x", b")"], b""), ([b"x", b"-a", b""], b""),
        ([b"", b"-o", b"x"], b""), ([b"1", b"-eq", b"bad"], b""),
    ],
    b"who": [
        ([], b""), ([b"-a"], b""), ([b"-b"], b""), ([b"-q"], b""),
        ([b"-H"], b""), ([b"-u"], b""), ([b"-x"], b""),
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
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
    )
    return (
        process.returncode,
        normalize_output(process.stdout, cwd),
        normalize_output(process.stderr, cwd),
    )


def snapshot(directory: Path) -> list[dict[str, object]]:
    paths: list[bytes] = []
    root = os.fsencode(directory)
    for current, directories, files in os.walk(root):
        directories.sort()
        files.sort()
        paths.extend(os.path.join(current, name) for name in [*directories, *files])
    hardlinks: dict[tuple[int, int], int] = {}
    records: list[dict[str, object]] = []
    for path in paths:
        metadata = os.lstat(path)
        record: dict[str, object] = {
            "name": os.path.relpath(path, root).hex(),
            "mode": stat.S_IMODE(metadata.st_mode), "size": metadata.st_size,
        }
        if stat.S_ISLNK(metadata.st_mode):
            record.update(kind="symlink", target=os.fsencode(os.readlink(path)).hex())
        elif stat.S_ISREG(metadata.st_mode):
            key = (metadata.st_dev, metadata.st_ino)
            record.update(
                kind="regular", data=Path(os.fsdecode(path)).read_bytes().hex(),
                hardlink=hardlinks.setdefault(key, len(hardlinks)), nlink=metadata.st_nlink,
            )
        elif stat.S_ISDIR(metadata.st_mode):
            record["kind"] = "directory"
        else:
            record["kind"] = "other"
        records.append(record)
    return records


Setup = Callable[[Path], tuple[list[bytes], bytes]]


def plain(arguments: list[bytes], input_bytes: bytes = b"") -> Setup:
    return lambda _directory: (arguments, input_bytes)


def file_case(name: str, data: bytes, arguments: list[bytes]) -> Setup:
    def setup(directory: Path) -> tuple[list[bytes], bytes]:
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return arguments, b""
    return setup


def csplit_case(arguments: list[bytes], data: bytes = b"a\nb\nc\nd\n") -> Setup:
    return file_case("input", data, [b"input", *arguments])


def join_case(arguments: list[bytes], left: bytes, right: bytes) -> Setup:
    def setup(directory: Path) -> tuple[list[bytes], bytes]:
        (directory / "left").write_bytes(left)
        (directory / "right").write_bytes(right)
        return [*arguments, b"left", b"right"], b""
    return setup


def ln_case(arguments: list[bytes]) -> Setup:
    def setup(directory: Path) -> tuple[list[bytes], bytes]:
        (directory / "source").write_bytes(b"payload\n")
        return arguments, b""
    return setup


def ln_directory(directory: Path) -> tuple[list[bytes], bytes]:
    (directory / "source").write_bytes(b"payload\n")
    (directory / "dest").mkdir()
    return [b"source", b"dest"], b""


def rm_tree(directory: Path) -> tuple[list[bytes], bytes]:
    (directory / "tree" / "sub").mkdir(parents=True)
    (directory / "tree" / "one").write_bytes(b"one")
    (directory / "tree" / "sub" / "two").write_bytes(b"two")
    (directory / "tree" / "link").symlink_to("sub/two")
    return [b"-r", b"tree"], b""


def rm_symlink(directory: Path) -> tuple[list[bytes], bytes]:
    (directory / "target").write_bytes(b"keep")
    (directory / "link").symlink_to("target")
    return [b"link"], b""


def shred_case(arguments: list[bytes], data: bytes = b"payload\n") -> Setup:
    def setup(directory: Path) -> tuple[list[bytes], bytes]:
        (directory / "input").write_bytes(data)
        (directory / "random").write_bytes(bytes(range(256)) * 512)
        return [b"--random-source=random", *arguments, b"input"], b""
    return setup


FILESYSTEM: dict[bytes, list[tuple[str, Setup]]] = {
    b"csplit": [
        ("line", csplit_case([b"2"])), ("repeat", csplit_case([b"2", b"{1}"])),
        ("regex", csplit_case([b"/c/"])), ("suppress", csplit_case([b"-s", b"2"])),
        ("prefix", csplit_case([b"-f", b"part-", b"-b", b"%03d", b"2"])),
        ("stdin", plain([b"-", b"2"], b"a\nb\nc\n")),
        ("missing", plain([b"missing", b"2"])),
    ],
    b"expand": [
        ("file", file_case("input", b"a\tb\n", [b"-t", b"4", b"input"])),
        ("missing", plain([b"missing"])),
    ],
    b"head": [
        ("file", file_case("input", b"a\nb\nc\n", [b"-n", b"2", b"input"])),
        ("two-files", join_case([b"-n", b"1"], b"a\nb\n", b"c\nd\n")),
        ("missing", plain([b"missing"])),
    ],
    b"join": [
        ("basic", join_case([], b"1 a\n2 b\n", b"1 x\n3 y\n")),
        ("all", join_case([b"-a1", b"-a2"], b"1 a\n2 b\n", b"1 x\n3 y\n")),
        ("separator", join_case([b"-t", b":"], b"1:a\n2:b\n", b"1:x\n2:y\n")),
        ("field", join_case([b"-1", b"2", b"-2", b"2"], b"a 1\nb 2\n", b"x 1\ny 3\n")),
        ("zero", join_case([b"-z"], b"1 a\0" b"2 b\0", b"1 x\0" b"3 y\0")),
        ("missing", plain([b"missing", b"also-missing"])),
    ],
    b"ln": [
        ("hard", ln_case([b"source", b"dest"])),
        ("symbolic", ln_case([b"-s", b"source", b"dest"])),
        ("relative", ln_case([b"-sr", b"source", b"dest"])),
        ("force", ln_case([b"-sf", b"source", b"dest"])),
        ("directory", ln_directory), ("missing", plain([b"missing", b"dest"])),
    ],
    b"rm": [
        ("file", file_case("victim", b"data", [b"victim"])),
        ("force-missing", plain([b"-f", b"missing"])), ("tree", rm_tree),
        ("symlink", rm_symlink),
        ("directory-error", file_case("directory/file", b"", [b"directory"])),
    ],
    b"shred": [
        ("one-pass", shred_case([b"-n", b"1"])),
        ("zero", shred_case([b"-n", b"0", b"-z"])),
        ("size", shred_case([b"-n", b"0", b"-s", b"32"])),
        ("remove", shred_case([b"-n", b"0", b"-u"])),
        ("missing", plain([b"missing"])),
    ],
    b"test": [
        ("regular", file_case("file", b"data", [b"-f", b"file"])),
        ("directory", plain([b"-d", b"."])), ("missing", plain([b"-e", b"missing"])),
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
    with tempfile.TemporaryDirectory(prefix="rustbox-small-07-") as temporary:
        root = Path(temporary)
        links = root / "invoke"
        links.mkdir()

        def link(applet: bytes) -> Path:
            return links / os.fsdecode(applet)

        for applet, cases in STATELESS.items():
            extra = [] if applet == b"test" else [(item, b"") for item in OPTIONS]
            for locale in LOCALES:
                for mode in ("explicit", "argv0"):
                    for arguments, input_bytes in [*cases, *extra]:
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

    applets = [b"csplit", b"expand", b"expr", b"head", b"join", b"ln", b"rm", b"shred", b"test", b"who"]
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
