#!/usr/bin/env python3
"""Differential public and filesystem checks for Coreutils small batch 09."""

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
    b"[": [
        ([], b""), ([b"x", b"]"], b""), ([b"", b"]"], b""),
        ([b"1", b"=", b"1", b"]"], b""), ([b"1", b"-eq", b"2", b"]"], b""),
        ([b"!", b"x", b"]"], b""), ([b"(", b"x", b")", b"]"], b""),
        ([b"x", b"-a", b"y", b"]"], b""),
    ],
    b"b2sum": [
        ([], b"hello\n"), ([b"--tag"], b"hello\n"),
        ([b"--length=128"], b"hello\n"), ([b"--binary"], b"\x00\xffdata"),
        ([b"--check"], b"invalid checksum line\n"), ([b"-x"], b""),
    ],
    b"chmod": [([], b""), ([b"600"], b""), ([b"-x"], b"")],
    b"dd": [
        ([b"status=none"], b"hello\n"),
        ([b"bs=2", b"count=2", b"status=none"], b"abcdef"),
        ([b"conv=ucase", b"status=none"], b"Abc\n"),
        ([b"if=/dev/null", b"of=/dev/null", b"status=none"], b""),
        ([b"bad=operand", b"status=none"], b""),
    ],
    b"df": [
        ([b"--output=source,fstype", b"."], b""),
        ([b"--output=target", b"."], b""),
        ([b"-P", b"--output=source", b"."], b""),
        ([b"--type=definitely-missing", b"."], b""), ([b"-x"], b""),
    ],
    b"du": [
        ([b"--apparent-size", b"-b", b"/dev/null"], b""),
        ([b"--inodes", b"/dev/null"], b""),
        ([b"--max-depth=0", b"/dev/null"], b""),
        ([b"--exclude=*", b"/dev/null"], b""), ([b"-x", b"/dev/null"], b""),
    ],
    b"split": [([b"--number=bad"], b""), ([b"-x"], b"")],
    b"tail": [
        ([], b"a\nb\nc\n"), ([b"-n", b"2"], b"a\nb\nc\n"),
        ([b"-n", b"+2"], b"a\nb\nc\n"), ([b"-c", b"3"], b"abcdef"),
        ([b"-z", b"-n", b"1"], b"a\0b\0"), ([b"-x"], b""),
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


def one_file(arguments: list[bytes], data: bytes = b"alpha\nbeta\ngamma\n", mode: int = 0o644) -> Setup:
    def setup(directory: Path) -> tuple[list[bytes], bytes]:
        path = directory / "input"
        path.write_bytes(data)
        path.chmod(mode)
        return arguments, b""
    return setup


def raw_file(arguments: list[bytes]) -> Setup:
    def setup(directory: Path) -> tuple[list[bytes], bytes]:
        name = b"raw-\xff"
        fd = os.open(os.path.join(os.fsencode(directory), name), os.O_WRONLY | os.O_CREAT, 0o640)
        os.write(fd, b"raw payload\n")
        os.close(fd)
        return [*arguments, name], b""
    return setup


def chmod_tree(directory: Path) -> tuple[list[bytes], bytes]:
    (directory / "tree" / "sub").mkdir(parents=True)
    (directory / "tree" / "sub" / "file").write_bytes(b"data")
    (directory / "tree" / "link").symlink_to("sub/file")
    return [b"-R", b"u=rwX,go=rX", b"tree"], b""


def bracket_file(directory: Path) -> tuple[list[bytes], bytes]:
    (directory / "file").write_bytes(b"data")
    return [b"-f", b"file", b"]"], b""


def dd_copy(directory: Path) -> tuple[list[bytes], bytes]:
    (directory / "input").write_bytes(b"abcdef\x00ghi")
    return [b"if=input", b"of=output", b"bs=3", b"status=none"], b""


def dd_seek(directory: Path) -> tuple[list[bytes], bytes]:
    (directory / "output").write_bytes(b"0123456789")
    return [b"of=output", b"bs=2", b"seek=2", b"conv=notrunc", b"status=none"], b"XY"


def du_tree(directory: Path) -> tuple[list[bytes], bytes]:
    (directory / "tree" / "sub").mkdir(parents=True)
    (directory / "tree" / "a").write_bytes(b"a" * 17)
    (directory / "tree" / "sub" / "b").write_bytes(b"b" * 33)
    os.link(directory / "tree" / "a", directory / "tree" / "hard")
    return [b"--apparent-size", b"-b", b"tree"], b""


def split_filter(directory: Path) -> tuple[list[bytes], bytes]:
    return [b"-C", b"4", b"--filter=cat > $FILE.copy", b"-", b"part-"], b"abcdefghij"


FILESYSTEM: dict[bytes, list[tuple[str, Setup]]] = {
    b"[": [("file", bracket_file), ("missing", plain([b"-e", b"missing", b"]"])),
           ("mode", one_file([b"-r", b"input", b"]"]))],
    b"b2sum": [
        ("file", one_file([b"input"])), ("raw-name", raw_file([])),
        ("missing", plain([b"missing"])),
    ],
    b"chmod": [
        ("numeric", one_file([b"600", b"input"])),
        ("symbolic", one_file([b"u+x,g-w", b"input"], mode=0o664)),
        ("reference", one_file([b"--reference=input", b"input"])),
        ("recursive", chmod_tree), ("missing", plain([b"600", b"missing"])),
    ],
    b"dd": [
        ("copy", dd_copy), ("seek", dd_seek),
        ("stdin", plain([b"of=output", b"status=none"], b"stdin-data")),
        ("swab", plain([b"of=output", b"conv=swab", b"status=none"], b"abcde")),
        ("missing", plain([b"if=missing", b"of=output", b"status=none"])),
    ],
    b"df": [
        ("types", plain([b"--output=source,fstype,target", b"."])),
        ("portable", plain([b"-P", b"--output=source,target", b"."])),
    ],
    b"du": [
        ("tree", du_tree), ("all", one_file([b"--apparent-size", b"-ab", b"."], b"payload")),
        ("exclude", one_file([b"--exclude=input", b"--apparent-size", b"-b", b"."])),
        ("raw-name", raw_file([b"--apparent-size", b"-b"])),
        ("missing", plain([b"missing"])),
    ],
    b"split": [
        ("bytes", plain([b"-b", b"3", b"-", b"part-"], b"abcdefghij")),
        ("lines", plain([b"-l", b"2", b"-", b"part-"], b"a\nb\nc\nd\ne\n")),
        ("number", plain([b"-n", b"3", b"-", b"part-"], b"abcdefghij")),
        ("numeric-suffix", plain([b"-b", b"2", b"-d", b"-", b"part-"], b"abcdef")),
        ("filter", split_filter), ("file", one_file([b"-b", b"4", b"input", b"part-"])),
    ],
    b"tail": [
        ("lines", one_file([b"-n", b"2", b"input"])),
        ("bytes", one_file([b"-c", b"5", b"input"])),
        ("from", one_file([b"-n", b"+2", b"input"])),
        ("zero", one_file([b"-z", b"-n", b"1", b"input"], b"a\0b\0")),
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
    with tempfile.TemporaryDirectory(prefix="rustbox-small-09-") as temporary:
        root = Path(temporary)
        links = root / "invoke"
        links.mkdir()

        def link(applet: bytes) -> Path:
            return links / os.fsdecode(applet)

        for applet, cases in STATELESS.items():
            for locale in LOCALES:
                for mode in ("explicit", "argv0"):
                    for arguments, input_bytes in [*cases, *[(option, b"") for option in OPTIONS]]:
                        expected = run(canonical, link(applet), applet, arguments, input_bytes, mode, locale)
                        actual = run(hybrid, link(applet), applet, arguments, input_bytes, mode, locale)
                        if actual != expected:
                            raise AssertionError((applet, locale, mode, arguments, expected, actual))
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

    applets = [b"[", b"b2sum", b"chmod", b"dd", b"df", b"du", b"split", b"tail"]
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
