#!/usr/bin/env python3
"""Differential public and filesystem checks for Coreutils small batch 11."""

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
    b"id": [
        ([], b""), ([b"-u"], b""), ([b"-g"], b""), ([b"-G"], b""),
        ([b"-un"], b""), ([b"-gn"], b""), ([b"-Gz"], b""), ([b"-x"], b""),
    ],
    b"ls": [
        ([], b""), ([b"-a"], b""), ([b"-l"], b""), ([b"-1"], b""),
        ([b"--color=never"], b""), ([b"--quoting-style=shell"], b""),
        ([b"--time-style=full-iso"], b""), ([b"-x"], b""),
    ],
    b"mkdir": [
        ([], b""), ([b"--mode=755"], b""), ([b"--parents"], b""), ([b"-x"], b""),
    ],
    b"stat": [
        ([b"/dev/null"], b""), ([b"-c", b"%s|%f|%a|%F", b"/dev/null"], b""),
        ([b"--printf=%s\\n", b"/dev/null"], b""),
        ([b"-L", b"-c", b"%F", b"/dev/null"], b""),
        ([b"-t", b"/dev/null"], b""), ([b"missing-rustbox-path"], b""), ([b"-x"], b""),
    ],
}


def environment(locale: str, cwd: Path | None = None) -> dict[bytes, bytes]:
    env = os.environb.copy()
    for name in (
        b"LANG", b"LANGUAGE", b"LC_ALL", b"LC_MESSAGES", b"QUOTING_STYLE",
        b"TIME_STYLE", b"COLUMNS", b"TZ",
    ):
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
                "mode": stat.S_IMODE(metadata.st_mode),
                "size": metadata.st_size,
                "uid": metadata.st_uid,
                "gid": metadata.st_gid,
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


def tree(arguments: list[bytes]) -> Setup:
    def setup(directory: Path) -> tuple[list[bytes], bytes]:
        (directory / "tree" / "sub").mkdir(parents=True)
        (directory / "tree" / "alpha").write_bytes(b"alpha\n")
        (directory / "tree" / "sub" / "beta").write_bytes(b"beta\n")
        (directory / "tree" / ".hidden").write_bytes(b"hidden\n")
        (directory / "tree" / "link").symlink_to("alpha")
        for path in (directory / "tree", directory / "tree" / "sub", directory / "tree" / "alpha", directory / "tree" / "sub" / "beta", directory / "tree" / ".hidden"):
            os.utime(path, (946684800, 946684800))
        os.utime(directory / "tree" / "link", (946684800, 946684800), follow_symlinks=False)
        return arguments, b""
    return setup


def raw_name(arguments: list[bytes]) -> Setup:
    def setup(directory: Path) -> tuple[list[bytes], bytes]:
        name = b"raw-\xff"
        fd = os.open(os.path.join(os.fsencode(directory), name), os.O_WRONLY | os.O_CREAT, 0o640)
        os.write(fd, b"raw payload\n")
        os.close(fd)
        os.utime(os.path.join(os.fsencode(directory), name), (946684800, 946684800))
        return [*arguments, name], b""
    return setup


FILESYSTEM: dict[bytes, list[tuple[str, Setup]]] = {
    b"ls": [
        ("tree", tree([b"-lA", b"--time-style=full-iso", b"tree"])),
        ("recursive", tree([b"-lAR", b"--time-style=full-iso", b"tree"])),
        ("classify", tree([b"-1F", b"tree"])),
        ("directory", tree([b"-ld", b"--time-style=full-iso", b"tree"])),
        ("raw-name", raw_name([b"-1", b"--quoting-style=shell-escape"])),
        ("missing", plain([b"missing"])),
    ],
    b"mkdir": [
        ("single", plain([b"directory"])),
        ("parents", plain([b"-p", b"one/two/three"])),
        ("mode", plain([b"-m", b"751", b"directory"])),
        ("verbose", plain([b"-pv", b"one/two"])),
        ("existing", tree([b"-p", b"tree/sub"])),
        ("missing-parent", plain([b"one/two"])),
    ],
    b"stat": [
        ("file", tree([b"-c", b"%n|%s|%f|%a|%F", b"tree/alpha"])),
        ("directory", tree([b"-c", b"%n|%f|%a|%F", b"tree/sub"])),
        ("symlink", tree([b"-c", b"%n|%N|%F", b"tree/link"])),
        ("dereference", tree([b"-L", b"-c", b"%n|%s|%F", b"tree/link"])),
        ("raw-name", raw_name([b"-c", b"%n|%s|%f|%a|%F"])),
        ("missing", plain([b"-c", b"%n|%F", b"missing"])),
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
    with tempfile.TemporaryDirectory(prefix="rustbox-small-11-") as temporary:
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

    result = {
        "schema": 1,
        "cases": checked,
        "passed": checked,
        "locales": LOCALES,
        "applets": ["id", "ls", "mkdir", "stat"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
