#!/usr/bin/env python3
"""Differential public and filesystem checks for Coreutils small batch 08."""

from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable


LOCALES = ["C", "en_US.UTF-8", "fr_FR", "tr_TR.UTF-8", "ja_JP.EUC-JP"]
OPTIONS = [[b"--help"], [b"--version"]]
STATELESS: dict[bytes, list[tuple[list[bytes], bytes]]] = {
    b"basenc": [
        ([b"--base64"], b"hello\n"), ([b"--base64", b"-d"], b"aGVsbG8K"),
        ([b"--base32"], b"hello\n"), ([b"--base32", b"-d"], b"NBSWY3DPEA======"),
        ([b"--base16"], b"\x00\xffabc"), ([b"--base16", b"-d"], b"00FF616263"),
        ([b"--base2msbf"], b"A"), ([b"--base2lsbf"], b"A"),
        ([b"--z85"], b"abcd"), ([b"--base64", b"-w", b"4"], b"abcdef"),
        ([b"--base64", b"-d"], b"invalid!"), ([b"-x"], b""),
    ],
    b"chown": [([], b""), ([b"invalid", b"missing"], b""), ([b"-x"], b"")],
    b"cut": [
        ([b"-b", b"1-3"], b"abcdef\n"), ([b"-c", b"2,4"], b"abcdef\n"),
        ([b"-d", b":", b"-f", b"2"], b"a:b:c\nx:y:z\n"),
        ([b"-d", b":", b"-f", b"1,3", b"--output-delimiter=|"], b"a:b:c\n"),
        ([b"-s", b"-d", b":", b"-f", b"2"], b"plain\na:b\n"),
        ([b"-z", b"-d", b":", b"-f", b"2"], b"a:b\0c:d\0"),
        ([b"-b", b"0"], b"abc\n"), ([b"-x"], b""),
    ],
    b"date": [
        ([b"-u", b"-d", b"@0", b"+%Y-%m-%dT%H:%M:%S%z"], b""),
        ([b"-u", b"-d", b"2000-02-29 12:34:56", b"+%s"], b""),
        ([b"-d", b"next Monday", b"+%u"], b""),
        ([b"--resolution"], b""), ([b"-d", b"invalid-date", b"+%s"], b""),
        ([b"-x"], b""),
    ],
    b"env": [
        ([], b""), ([b"-i"], b""), ([b"-i", b"A=one", b"B=two"], b""),
        ([b"-i", b"A=one", b"/usr/bin/printenv", b"A"], b""),
        ([b"-i", b"-u", b"A", b"A=one", b"/usr/bin/printenv", b"A"], b""),
        ([b"-S", b"/usr/bin/printf '%s:%s' one two"], b""),
        ([b"--null", b"-i", b"A=one"], b""), ([b"-x"], b""),
    ],
    b"pr": [
        ([], b"a\nb\nc\n"), ([b"-t"], b"a\nb\nc\n"),
        ([b"-t", b"-2"], b"a\nb\nc\nd\n"),
        ([b"-t", b"-w", b"20", b"-3"], b"a\nb\nc\nd\ne\nf\n"),
        ([b"-t", b"-n"], b"a\nb\n"), ([b"-t", b"-d"], b"a\nb\n"),
        ([b"-t", b"-s", b":"], b"a\nb\nc\nd\n"), ([b"-x"], b""),
    ],
    b"ptx": [
        ([b"-A", b"-"], b"alpha beta\nbeta gamma\n"),
        ([b"-G", b"-"], b"alpha beta\n"),
        ([b"-f", b"-"], b"Alpha beta\n"), ([b"-x"], b""),
    ],
    b"stty": [([], b""), ([b"-a"], b""), ([b"size"], b""), ([b"invalid"], b""), ([b"-x"], b"")],
    b"tr": [
        ([b"a-z", b"A-Z"], b"alpha beta\n"), ([b"-d", b"0-9"], b"a1b2c3\n"),
        ([b"-s", b" "], b"a   b    c\n"), ([b"-ds", b"0-9", b" "], b"a1   b2\n"),
        ([b"[:lower:]", b"[:upper:]"], b"Abc XYZ\n"),
        ([b"-c", b"a-z", b"?"], b"abc123\n"), ([b"[a*3]", b"x"], b"aaaab\n"),
        ([b"-x"], b""),
    ],
    b"unexpand": [
        ([], b"        a\n"), ([b"-a"], b"a       b\n"),
        ([b"-t", b"4"], b"    a        b\n"),
        ([b"-t", b"2,6"], b"      a\n"), ([b"-t", b"+4"], b"        a\n"),
        ([b"-t", b"/4"], b"        a\n"), ([], b"\xff       x\n"),
        ([b"-x"], b""),
    ],
}


def environment(locale: str, cwd: Path | None = None) -> dict[bytes, bytes]:
    env = os.environb.copy()
    for name in (b"LANG", b"LANGUAGE", b"LC_ALL", b"LC_MESSAGES", b"QUOTING_STYLE", b"TZ"):
        env.pop(name, None)
    env[b"LC_ALL"] = locale.encode()
    env[b"TZ"] = b"UTC0"
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
    return process.returncode, normalize_output(process.stdout, cwd), normalize_output(process.stderr, cwd)


def compare_stateless(canonical: Path, hybrid: Path, link: Path, applet: bytes,
                      arguments: list[bytes], data: bytes, mode: str, locale: str) -> None:
    # pr reads CLOCK_REALTIME when formatting the default header for stdin.
    # Compare both commands within one UTC minute, including the full header.
    timed_header = applet == b"pr" and not arguments
    for _ in range(3):
        minute = time.time_ns() // 60_000_000_000 if timed_header else None
        expected = run(canonical, link, applet, arguments, data, mode, locale)
        actual = run(hybrid, link, applet, arguments, data, mode, locale)
        if timed_header and time.time_ns() // 60_000_000_000 != minute:
            continue
        if actual != expected:
            raise AssertionError((applet, locale, mode, arguments, expected, actual))
        return
    raise RuntimeError("could not compare the two default pr headers within one minute")


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
                "name": os.path.relpath(path, root).hex(),
                "mode": stat.S_IMODE(metadata.st_mode), "size": metadata.st_size,
                "uid": metadata.st_uid, "gid": metadata.st_gid,
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


def file_case(arguments: list[bytes], data: bytes = b"alpha:beta:gamma\n") -> Setup:
    def setup(directory: Path) -> tuple[list[bytes], bytes]:
        (directory / "input").write_bytes(data)
        return arguments, b""
    return setup


def chown_file(arguments: list[bytes]) -> Setup:
    def setup(directory: Path) -> tuple[list[bytes], bytes]:
        (directory / "file").write_bytes(b"data")
        return arguments, b""
    return setup


def chown_tree(directory: Path) -> tuple[list[bytes], bytes]:
    (directory / "tree" / "sub").mkdir(parents=True)
    (directory / "tree" / "sub" / "file").write_bytes(b"data")
    (directory / "tree" / "link").symlink_to("sub/file")
    return [b"-R", b"1234:2345", b"tree"], b""


def date_reference(directory: Path) -> tuple[list[bytes], bytes]:
    path = directory / "reference"
    path.write_bytes(b"")
    os.utime(path, (946684800, 946684800))
    return [b"-u", b"-r", b"reference", b"+%s"], b""


FILESYSTEM: dict[bytes, list[tuple[str, Setup]]] = {
    b"basenc": [
        ("encode", file_case([b"--base64", b"input"], b"binary\x00\xff\n")),
        ("decode", file_case([b"--base16", b"-d", b"input"], b"00FF616263")),
        ("missing", plain([b"--base64", b"missing"])),
    ],
    b"chown": [
        ("numeric", chown_file([b"1234:2345", b"file"])),
        ("from", chown_file([b"--from=0:0", b"1234:2345", b"file"])),
        ("recursive", chown_tree), ("missing", plain([b"1234:2345", b"missing"])),
    ],
    b"cut": [
        ("fields", file_case([b"-d", b":", b"-f", b"2", b"input"])),
        ("bytes", file_case([b"-b", b"2-4", b"input"], b"abcdef\n")),
        ("missing", plain([b"-b", b"1", b"missing"])),
    ],
    b"date": [("reference", date_reference)],
    b"pr": [
        ("file", file_case([b"-t", b"input"], b"a\nb\nc\n")),
        ("columns", file_case([b"-t", b"-2", b"input"], b"a\nb\nc\nd\n")),
        ("missing", plain([b"missing"])),
    ],
    b"ptx": [
        ("traditional", file_case([b"-A", b"input"], b"alpha beta\nbeta gamma\n")),
        ("gnu", file_case([b"-G", b"input"], b"alpha beta\n")),
        ("missing", plain([b"missing"])),
    ],
    b"unexpand": [
        ("file", file_case([b"-a", b"input"], b"a       b\n")),
        ("tabs", file_case([b"-t", b"4", b"input"], b"        a\n")),
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
    with tempfile.TemporaryDirectory(prefix="rustbox-small-08-") as temporary:
        root = Path(temporary)
        links = root / "invoke"
        links.mkdir()

        def link(applet: bytes) -> Path:
            return links / os.fsdecode(applet)

        for applet, cases in STATELESS.items():
            for locale in LOCALES:
                for mode in ("explicit", "argv0"):
                    for arguments, input_bytes in [*cases, *[(option, b"") for option in OPTIONS]]:
                        compare_stateless(canonical, hybrid, link(applet), applet, arguments, input_bytes, mode, locale)
                        checked += 1

        for applet, cases in FILESYSTEM.items():
            for locale in LOCALES:
                for mode in ("explicit", "argv0"):
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

    applets = [b"basenc", b"chown", b"cut", b"date", b"env", b"pr", b"ptx", b"stty", b"tr", b"unexpand"]
    result = {
        "schema": 1, "cases": checked, "passed": checked, "locales": LOCALES,
        "applets": [os.fsdecode(applet) for applet in applets],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
