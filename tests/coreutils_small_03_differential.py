#!/usr/bin/env python3
"""Differential public and filesystem checks for Coreutils small batch 03."""

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
CHECKSUMS = [b"md5sum", b"sha1sum", b"sha224sum", b"sha256sum", b"sha384sum", b"sha512sum"]
STATELESS: dict[bytes, list[tuple[list[bytes], bytes]]] = {
    b"nohup": [
        ([], b""),
        ([b"/bin/sh", b"-c", b"printf nohup"], b""),
        ([b"/bin/sh", b"-c", b"exit 7"], b""),
        ([b"missing-rustbox-command"], b""),
        ([b"-x"], b""),
    ],
}
for checksum in CHECKSUMS:
    STATELESS[checksum] = [
        ([], b""),
        ([], b"abc"),
        ([b"-"], b"abc\x00\xff"),
        ([b"--binary", b"-"], b"payload"),
        ([b"--tag", b"-"], b"payload"),
        ([b"missing"], b""),
        ([b"-x"], b""),
    ]


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
    input_bytes: bytes,
    mode: str,
    locale: str,
    cwd: Path | None = None,
) -> tuple[int, bytes, bytes]:
    process = subprocess.run(
        command(binary, link, applet, arguments, mode),
        cwd=cwd,
        env=environment(locale),
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=15,
    )
    stdout, stderr = process.stdout, process.stderr
    if cwd is not None:
        encoded = os.fsencode(cwd)
        stdout = stdout.replace(encoded, b"$CWD")
        stderr = stderr.replace(encoded, b"$CWD")
    return process.returncode, stdout, stderr


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
            record: dict[str, object] = {
                "name": relative.hex(),
                "mode": stat.S_IMODE(metadata.st_mode),
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


def listing(directory: Path, arguments: list[bytes]) -> tuple[list[bytes], bytes]:
    (directory / "alpha").write_bytes(b"alpha\n")
    (directory / "space name").write_bytes(b"space\n")
    (directory / ".hidden").write_bytes(b"hidden\n")
    (directory / "subdir").mkdir()
    (directory / "link").symlink_to("alpha")
    for path in directory.iterdir():
        os.utime(path, (1_000_000_000, 1_000_000_000), follow_symlinks=False)
    return arguments, b""


def checksum_files(directory: Path, arguments: list[bytes]) -> tuple[list[bytes], bytes]:
    (directory / "plain").write_bytes(b"abc")
    descriptor = os.open(os.path.join(os.fsencode(directory), b"\xff"), os.O_CREAT | os.O_WRONLY, 0o640)
    os.write(descriptor, b"raw\x00bytes")
    os.close(descriptor)
    return arguments, b""


def chgrp_file(directory: Path, arguments: list[bytes]) -> tuple[list[bytes], bytes]:
    (directory / "file").write_bytes(b"payload")
    return arguments, b""


def chgrp_tree(directory: Path, arguments: list[bytes]) -> tuple[list[bytes], bytes]:
    (directory / "tree").mkdir()
    (directory / "tree" / "file").write_bytes(b"payload")
    (directory / "tree" / "link").symlink_to("file")
    return arguments, b""


FILESYSTEM: dict[bytes, list[tuple[str, Setup]]] = {
    b"chgrp": [
        ("none", plain([])),
        ("missing-group", plain([b"missing-rustbox-group", b"file"])),
        ("current-group", lambda d: chgrp_file(d, [str(os.getgid()).encode(), b"file"])),
        ("recursive", lambda d: chgrp_tree(d, [b"-R", str(os.getgid()).encode(), b"tree"])),
    ],
    b"dir": [
        ("default", lambda d: listing(d, [])),
        ("all", lambda d: listing(d, [b"-a"])),
        ("long", lambda d: listing(d, [b"-l", b"--time-style=+%s"])),
        ("quote", lambda d: listing(d, [b"-Q"])),
    ],
    b"vdir": [
        ("default", lambda d: listing(d, [])),
        ("all", lambda d: listing(d, [b"-a"])),
        ("one", lambda d: listing(d, [b"-1"])),
        ("quote", lambda d: listing(d, [b"-Q"])),
    ],
}
for checksum in CHECKSUMS:
    FILESYSTEM[checksum] = [
        ("plain", lambda d: checksum_files(d, [b"plain"])),
        ("binary", lambda d: checksum_files(d, [b"--binary", b"plain"])),
        ("tag", lambda d: checksum_files(d, [b"--tag", b"plain"])),
        ("raw", lambda d: checksum_files(d, [b"\xff"])),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--hybrid", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    canonical = args.canonical.resolve()
    hybrid = args.hybrid.resolve()
    checked = 0
    with tempfile.TemporaryDirectory(prefix="rustbox-small-03-") as temporary:
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
                        expected = run(
                            canonical, link(applet), applet, expected_args, expected_input,
                            mode, locale, expected_dir,
                        )
                        actual = run(
                            hybrid, link(applet), applet, actual_args, actual_input,
                            mode, locale, actual_dir,
                        )
                        if actual != expected or snapshot(actual_dir) != snapshot(expected_dir):
                            raise AssertionError(
                                (applet, locale, mode, name, expected, actual,
                                 snapshot(expected_dir), snapshot(actual_dir))
                            )
                        checked += 1

    result = {
        "schema": 1,
        "cases": checked,
        "passed": checked,
        "locales": LOCALES,
        "applets": [os.fsdecode(item) for item in [b"chgrp", b"dir", *CHECKSUMS, b"nohup", b"vdir"]],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
