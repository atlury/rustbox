#!/usr/bin/env python3
"""Differential public and filesystem checks for Coreutils small batch 04."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Callable


LOCALES = ["C", "en_US.UTF-8", "fr_FR", "tr_TR.UTF-8", "ja_JP.EUC-JP"]
OPTIONS = [[b"--help"], [b"--version"]]
STATELESS: dict[bytes, list[tuple[list[bytes], bytes]]] = {
    b"base64": [
        ([], b""), ([], b"abc"), ([], b"\x00\xffbinary\n"),
        ([b"--wrap=4"], b"abcdef"), ([b"--wrap=0"], b"abcdef"),
        ([b"--decode"], b"YWJjCg==\n"), ([b"-di"], b"Y W!Jj\n"),
        ([b"--decode"], b"invalid!"), ([b"-x"], b""),
    ],
    b"groups": [([], b""), ([b"root"], b""), ([b"missing-rustbox-user"], b""), ([b"-x"], b"")],
    b"pathchk": [
        ([], b""), ([b"."], b""), ([b"/"], b""), ([b"a/b/c"], b""),
        ([b"-p", b"portable-name"], b""), ([b"-P", b"-bad"], b""),
        ([b"--", b"-leading"], b""), ([b"\xff/\xfe"], b""), ([b"-x"], b""),
    ],
    b"pwd": [([], b""), ([b"-L"], b""), ([b"-P"], b""), ([b"extra"], b""), ([b"-x"], b"")],
    b"runcon": [
        ([], b""), ([b"missing-context", b"/bin/true"], b""),
        ([b"-u", b"user", b"/bin/true"], b""), ([b"-x"], b""),
    ],
    b"stdbuf": [
        ([], b""), ([b"-o0", b"/bin/sh", b"-c", b"printf unbuffered"], b""),
        ([b"-oL", b"/bin/sh", b"-c", b"printf line"], b""),
        ([b"-i0", b"-o0", b"/bin/sh", b"-c", b"cat"], b"stdin\x00bytes"),
        ([b"-oBAD", b"/bin/true"], b""), ([b"-x"], b""),
    ],
    b"tsort": [
        ([], b""), ([], b"a b\nb c\n"), ([], b"a b\nb a\n"),
        ([b"-"], b"one two\nthree four\n"), ([], b"odd\n"), ([b"-x"], b""),
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


def normalize_output(applet: bytes, data: bytes, cwd: Path | None) -> bytes:
    if cwd is not None:
        data = data.replace(os.fsencode(cwd), b"$CWD")
    if applet == b"mktemp":
        data = re.sub(rb"(temp|directory)\.[A-Za-z0-9]{6}", rb"\1.$RANDOM", data)
    return data


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
        normalize_output(applet, process.stdout, cwd),
        normalize_output(applet, process.stderr, cwd),
    )


def normalized_name(name: bytes) -> str:
    text = os.fsdecode(name).encode("unicode_escape").decode("ascii")
    return re.sub(r"^(temp|directory)\.[A-Za-z0-9]{6}$", r"\1.$RANDOM", text)


def snapshot(directory: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    root = os.fsencode(directory)
    for current, directories, files in os.walk(root):
        directories.sort()
        files.sort()
        for name in [*directories, *files]:
            path = os.path.join(current, name)
            metadata = os.lstat(path)
            relative = os.path.relpath(path, root)
            parts = relative.split(b"/")
            shown = "/".join(normalized_name(part) for part in parts)
            record: dict[str, object] = {
                "name": shown,
                "mode": stat.S_IMODE(metadata.st_mode),
                "size": metadata.st_size,
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


def base64_file(directory: Path) -> tuple[list[bytes], bytes]:
    (directory / "input").write_bytes(b"\x00data\xff")
    return [b"input"], b""


def comm_files(directory: Path, arguments: list[bytes], zero: bool = False) -> tuple[list[bytes], bytes]:
    separator = b"\0" if zero else b"\n"
    (directory / "left").write_bytes(separator.join([b"alpha", b"common", b"left"]) + separator)
    (directory / "right").write_bytes(separator.join([b"beta", b"common", b"right"]) + separator)
    return arguments, b""


def truncate_file(directory: Path, arguments: list[bytes]) -> tuple[list[bytes], bytes]:
    (directory / "file").write_bytes(b"0123456789")
    return arguments, b""


def truncate_link(directory: Path, arguments: list[bytes]) -> tuple[list[bytes], bytes]:
    (directory / "target").write_bytes(b"0123456789")
    (directory / "link").symlink_to("target")
    return arguments, b""


FILESYSTEM: dict[bytes, list[tuple[str, Setup]]] = {
    b"base64": [
        ("file", base64_file),
    ],
    b"comm": [
        ("default", lambda d: comm_files(d, [b"left", b"right"])),
        ("suppress", lambda d: comm_files(d, [b"-12", b"left", b"right"])),
        ("check", lambda d: comm_files(d, [b"--check-order", b"left", b"right"])),
        ("zero", lambda d: comm_files(d, [b"-z", b"left", b"right"], True)),
        ("missing", plain([b"left", b"right"])),
    ],
    b"mktemp": [
        ("file", plain([b"temp.XXXXXX"])),
        ("directory", plain([b"-d", b"directory.XXXXXX"])),
        ("dry-run", plain([b"-u", b"temp.XXXXXX"])),
        ("invalid", plain([b"no-X-template"])),
    ],
    b"truncate": [
        ("shrink", lambda d: truncate_file(d, [b"-s", b"4", b"file"])),
        ("grow", lambda d: truncate_file(d, [b"-s", b"20", b"file"])),
        ("relative", lambda d: truncate_file(d, [b"-s", b"+5", b"file"])),
        ("reference", lambda d: truncate_file(d, [b"-r", b"file", b"new"])),
        ("symlink", lambda d: truncate_link(d, [b"-s", b"3", b"link"])),
        ("missing-no-create", plain([b"-c", b"-s", b"1", b"missing"])),
    ],
}


def paired_stdbuf_layout(canonical: Path, hybrid: Path, root: Path) -> tuple[Path, Path, dict]:
    """Compare relocated binaries with the same Coreutils child-process helper available."""
    helper = canonical.with_name("libstdbuf.so")
    binaries = []
    for name, source in (("oracle", canonical), ("candidate", hybrid)):
        directory = root / name
        directory.mkdir()
        binary = directory / source.name
        shutil.copy2(source, binary)
        if hashlib.sha256(binary.read_bytes()).digest() != hashlib.sha256(source.read_bytes()).digest():
            raise ValueError("relocation changed the executable bytes")
        binaries.append(binary)

    missing = {}
    for mode in ("explicit", "argv0"):
        results = [run(binary, root / "invoke/stdbuf", b"stdbuf", [b"-o0", b"/bin/true"], b"", mode, "C")
                   for binary in binaries]
        if results[0] != results[1] or results[0][0] != 125 or b"libstdbuf.so" not in results[0][2]:
            raise ValueError(f"unexpected missing-helper behavior for {mode}: {results!r}")
        missing[mode] = results[0][0]
    # A bare applet name can resolve /proc/self/exe. An absolute argv[0]
    # lets GNU stdbuf also look beside the invocation symlink.
    for directory in [*(binary.parent for binary in binaries), root / "invoke"]:
        shutil.copy2(helper, directory / "libstdbuf.so")
    # One-byte output remains buffered on a pipe for line/full buffering.
    # Inspect the child stream before flushing, so scheduling cannot hide a missing preload.
    child = root / "probe-buffering"
    subprocess.run(["cc", "-x", "c", "-", "-o", child], check=True, input=b"""
#include <stdio.h>
#include <stdio_ext.h>
int main(void) {
    if (fputc('x', stdout) == EOF) return 2;
    fprintf(stderr, "%d %zu", !!__flbf(stdout), __fpending(stdout));
    return fflush(stdout) != 0;
}
""")
    buffering = {b"-o0": b"0 0", b"-oL": b"1 1", b"-o4096": b"0 1"}
    for binary in binaries:
        for mode in ("explicit", "argv0"):
            for option, observed in buffering.items():
                result = run(binary, root / "invoke/stdbuf", b"stdbuf", [option, os.fsencode(child)], b"", mode, "C")
                if result != (0, b"x", observed):
                    raise ValueError(f"unexpected child buffering for {binary.name} {mode} {option!r}: {result!r}")
    return binaries[0], binaries[1], {
        "helper_sha256": hashlib.sha256(helper.read_bytes()).hexdigest(), "helper_bytes": helper.stat().st_size,
        "missing_helper_status": missing, "child_buffering_cases_per_binary": 6,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--hybrid", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--relocate-stdbuf", action="store_true")
    args = parser.parse_args()
    canonical, hybrid = args.canonical.resolve(), args.hybrid.resolve()
    excluded = {item.encode() for item in args.exclude}
    unknown = excluded - set(STATELESS) - set(FILESYSTEM)
    if unknown:
        raise RuntimeError(f"unknown excluded applet: {sorted(unknown)!r}")
    checked = 0
    with tempfile.TemporaryDirectory(prefix="rustbox-small-04-") as temporary:
        root = Path(temporary)
        links = root / "invoke"
        links.mkdir()

        def link(applet: bytes) -> Path:
            return links / os.fsdecode(applet)

        stdbuf_pair = paired_stdbuf_layout(canonical, hybrid, root) if args.relocate_stdbuf else None
        for applet, cases in STATELESS.items():
            if applet in excluded:
                continue
            oracle, candidate = stdbuf_pair[:2] if applet == b"stdbuf" and stdbuf_pair else (canonical, hybrid)
            for locale in LOCALES:
                for mode in ("explicit", "argv0"):
                    for arguments, input_bytes in [*cases, *[(item, b"") for item in OPTIONS]]:
                        expected = run(oracle, link(applet), applet, arguments, input_bytes, mode, locale)
                        actual = run(candidate, link(applet), applet, arguments, input_bytes, mode, locale)
                        if actual != expected:
                            raise AssertionError((applet, locale, mode, arguments, expected, actual))
                        checked += 1

        for applet, cases in FILESYSTEM.items():
            if applet in excluded:
                continue
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
                        if actual != expected or snapshot(actual_dir) != snapshot(expected_dir):
                            raise AssertionError((applet, locale, mode, name, expected, actual, snapshot(expected_dir), snapshot(actual_dir)))
                        checked += 1

    result = {
        "schema": 1, "cases": checked, "passed": checked, "locales": LOCALES,
        "applets": [os.fsdecode(item) for item in [b"base64", b"comm", b"groups", b"mktemp", b"pathchk", b"pwd", b"runcon", b"stdbuf", b"truncate", b"tsort"] if item not in excluded],
    }
    if stdbuf_pair:
        result["stdbuf_relocation"] = stdbuf_pair[2]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
