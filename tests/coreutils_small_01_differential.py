#!/usr/bin/env python3
"""Differential public and filesystem checks for Coreutils small batch 01."""

from __future__ import annotations

import argparse
import json
import os
import signal
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Callable


LOCALES = ["C", "en_US.UTF-8", "fr_FR", "tr_TR.UTF-8", "ja_JP.EUC-JP"]
STATELESS: dict[bytes, list[list[bytes]]] = {
    b"basename": [
        [], [b"/usr/bin/sort"], [b"/usr/bin/sort", b"sort"],
        [b"-s", b".c", b"one.c", b"two"], [b"-a", b"a", b"b/"],
        [b"-z", b"a/b"], [b"--suffix=.c", b"a.c"], [b"-x"], [b"\xff"],
    ],
    b"dirname": [
        [], [b"/usr/bin"], [b"plain"], [b"/"], [b"//"], [b"a/b///"],
        [b"-z", b"a/b"], [b"-z", b"a", b"b/c"], [b"-x"], [b"\xff/\xfe"],
    ],
    b"hostid": [[], [b"extra"], [b"-x"]],
    b"logname": [[], [b"extra"], [b"-x"]],
    b"printenv": [
        [], [b"ENV_TEST"], [b"MISSING"], [b"ENV_TEST2", b"ENV_TEST"],
        [b"-0", b"ENV_TEST"], [b"--null", b"RAW_VALUE"], [b"-x"], [b"\xff"],
    ],
    b"tty": [[], [b"-s"], [b"extra"], [b"-s", b"extra"], [b"-x"]],
    b"whoami": [[], [b"extra"], [b"-x"]],
}
FINITE_OPTIONS = [[b"--help"], [b"--version"]]


def environment(locale: str) -> dict[bytes, bytes]:
    env = os.environb.copy()
    for name in (b"LANG", b"LANGUAGE", b"LC_ALL", b"LC_MESSAGES", b"QUOTING_STYLE"):
        env.pop(name, None)
    env.update(
        {
            b"LC_ALL": locale.encode(),
            b"ENV_TEST": b"alpha",
            b"ENV_TEST2": b"beta gamma",
            b"RAW_VALUE": b"\xff\xfe",
        }
    )
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
    return process.returncode, process.stdout, process.stderr


def broken_output(
    binary: Path, link: Path, applet: bytes, arguments: list[bytes], mode: str, locale: str
) -> tuple[int, bytes]:
    reader, writer = os.pipe()
    os.close(reader)
    try:
        process = subprocess.Popen(
            command(binary, link, applet, arguments, mode),
            env=environment(locale),
            stdin=subprocess.DEVNULL,
            stdout=writer,
            stderr=subprocess.PIPE,
        )
    finally:
        os.close(writer)
    stderr = process.communicate(timeout=10)[1]
    return process.returncode, stderr


def yes_prefix(
    binary: Path, link: Path, arguments: list[bytes], mode: str, locale: str
) -> tuple[bytes, bytes]:
    process = subprocess.Popen(
        command(binary, link, b"yes", arguments, mode),
        env=environment(locale),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    prefix = process.stdout.read(8192)
    process.send_signal(signal.SIGTERM)
    _, stderr = process.communicate(timeout=10)
    return prefix, stderr


def snapshot(directory: Path) -> dict[str, object]:
    root = os.fsencode(directory)
    records: list[dict[str, object]] = []
    inode_names: dict[tuple[int, int], list[str]] = {}
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        metadata = os.lstat(path)
        shown = os.fsdecode(name).encode("unicode_escape").decode("ascii")
        record: dict[str, object] = {
            "name": shown,
            "mode": stat.S_IMODE(metadata.st_mode),
            "nlink": metadata.st_nlink,
        }
        if stat.S_ISREG(metadata.st_mode):
            record["kind"] = "regular"
            record["data_hex"] = Path(os.fsdecode(path)).read_bytes().hex()
            inode_names.setdefault((metadata.st_dev, metadata.st_ino), []).append(shown)
        elif stat.S_ISLNK(metadata.st_mode):
            record["kind"] = "symlink"
            target = os.readlink(path)
            record["target"] = os.fsdecode(target).encode("unicode_escape").decode("ascii")
            inode_names.setdefault((metadata.st_dev, metadata.st_ino), []).append(shown)
        elif stat.S_ISDIR(metadata.st_mode):
            record["kind"] = "directory"
        else:
            record["kind"] = "other"
        records.append(record)
    hardlink_groups = sorted(sorted(names) for names in inode_names.values() if len(names) > 1)
    return {"entries": records, "hardlink_groups": hardlink_groups}


Setup = Callable[[Path], list[bytes]]


def no_files(arguments: list[bytes]) -> Setup:
    return lambda _directory: arguments


def link_regular(directory: Path) -> list[bytes]:
    (directory / "source").write_bytes(b"payload\x00")
    return [b"source", b"destination"]


def link_existing(directory: Path) -> list[bytes]:
    (directory / "source").write_bytes(b"source")
    (directory / "destination").write_bytes(b"destination")
    return [b"source", b"destination"]


def link_symlink(directory: Path) -> list[bytes]:
    (directory / "target").write_bytes(b"target")
    (directory / "source-link").symlink_to("target")
    return [b"source-link", b"destination-link"]


def link_raw(directory: Path) -> list[bytes]:
    descriptor = os.open(os.path.join(os.fsencode(directory), b"\xff"), os.O_CREAT | os.O_WRONLY, 0o640)
    os.write(descriptor, b"raw")
    os.close(descriptor)
    return [b"\xff", b"\xfe"]


def unlink_regular(directory: Path) -> list[bytes]:
    (directory / "victim").write_bytes(b"payload")
    return [b"victim"]


def unlink_symlink(directory: Path) -> list[bytes]:
    (directory / "target").write_bytes(b"target")
    (directory / "victim").symlink_to("target")
    return [b"victim"]


def unlink_directory(directory: Path) -> list[bytes]:
    (directory / "victim").mkdir()
    return [b"victim"]


def unlink_raw(directory: Path) -> list[bytes]:
    descriptor = os.open(os.path.join(os.fsencode(directory), b"\xff"), os.O_CREAT | os.O_WRONLY, 0o600)
    os.close(descriptor)
    return [b"\xff"]


FILESYSTEM_CASES: dict[bytes, list[tuple[str, Setup]]] = {
    b"link": [
        ("no-arguments", no_files([])),
        ("missing-source", no_files([b"missing", b"destination"])),
        ("too-many", no_files([b"a", b"b", b"c"])),
        ("regular", link_regular),
        ("existing-destination", link_existing),
        ("symlink", link_symlink),
        ("raw-name", link_raw),
    ],
    b"unlink": [
        ("no-arguments", no_files([])),
        ("missing", no_files([b"missing"])),
        ("too-many", no_files([b"a", b"b"])),
        ("regular", unlink_regular),
        ("symlink", unlink_symlink),
        ("directory", unlink_directory),
        ("raw-name", unlink_raw),
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
    with tempfile.TemporaryDirectory(prefix="rustbox-small-01-") as temporary:
        root = Path(temporary)
        link_root = root / "invoke"
        link_root.mkdir()

        def invocation_link(_which: str, applet: bytes) -> Path:
            return link_root / os.fsdecode(applet)

        for applet, cases in STATELESS.items():
            for locale in LOCALES:
                for mode in ("explicit", "argv0"):
                    for arguments in [*cases, *FINITE_OPTIONS]:
                        expected = run(
                            canonical, invocation_link("canonical", applet), applet,
                            arguments, mode, locale,
                        )
                        actual = run(
                            hybrid, invocation_link("hybrid", applet), applet,
                            arguments, mode, locale,
                        )
                        if actual != expected:
                            raise AssertionError((applet, locale, mode, arguments, expected, actual))
                        checked += 1

        for applet in FILESYSTEM_CASES:
            for locale in LOCALES:
                for mode in ("explicit", "argv0"):
                    for arguments in FINITE_OPTIONS:
                        expected = run(
                            canonical, invocation_link("canonical", applet), applet,
                            arguments, mode, locale,
                        )
                        actual = run(
                            hybrid, invocation_link("hybrid", applet), applet,
                            arguments, mode, locale,
                        )
                        if actual != expected:
                            raise AssertionError((applet, locale, mode, arguments, expected, actual))
                        checked += 1
                    for case_name, setup in FILESYSTEM_CASES[applet]:
                        pair = root / f"fs-{checked}"
                        canonical_cwd = pair / "canonical"
                        hybrid_cwd = pair / "hybrid"
                        canonical_cwd.mkdir(parents=True)
                        hybrid_cwd.mkdir()
                        canonical_arguments = setup(canonical_cwd)
                        hybrid_arguments = setup(hybrid_cwd)
                        if canonical_arguments != hybrid_arguments:
                            raise AssertionError((applet, case_name, "setup arguments"))
                        expected = run(
                            canonical, invocation_link("canonical", applet), applet,
                            canonical_arguments, mode, locale, canonical_cwd,
                        )
                        actual = run(
                            hybrid, invocation_link("hybrid", applet), applet,
                            hybrid_arguments, mode, locale, hybrid_cwd,
                        )
                        if actual != expected or snapshot(hybrid_cwd) != snapshot(canonical_cwd):
                            raise AssertionError((
                                applet, locale, mode, case_name, expected, actual,
                                snapshot(canonical_cwd), snapshot(hybrid_cwd),
                            ))
                        checked += 1

        for locale in LOCALES:
            for mode in ("explicit", "argv0"):
                for arguments in FINITE_OPTIONS:
                    expected = run(
                        canonical, invocation_link("canonical", b"yes"), b"yes",
                        arguments, mode, locale,
                    )
                    actual = run(
                        hybrid, invocation_link("hybrid", b"yes"), b"yes",
                        arguments, mode, locale,
                    )
                    if actual != expected:
                        raise AssertionError((b"yes", locale, mode, arguments, expected, actual))
                    checked += 1
                for arguments in ([], [b"word"], [b"alpha", b"beta"], [b""], [b"\xff"]):
                    expected = yes_prefix(
                        canonical, invocation_link("canonical", b"yes"), arguments, mode, locale
                    )
                    actual = yes_prefix(
                        hybrid, invocation_link("hybrid", b"yes"), arguments, mode, locale
                    )
                    if actual != expected:
                        raise AssertionError((b"yes", locale, mode, arguments, "prefix"))
                    checked += 1
                expected_broken = broken_output(
                    canonical, invocation_link("canonical", b"yes"), b"yes", [], mode, locale
                )
                actual_broken = broken_output(
                    hybrid, invocation_link("hybrid", b"yes"), b"yes", [], mode, locale
                )
                if actual_broken != expected_broken:
                    raise AssertionError((b"yes", locale, mode, "broken-output"))
                checked += 1

        for applet in [*STATELESS, *FILESYSTEM_CASES]:
            for locale in LOCALES:
                for mode in ("explicit", "argv0"):
                    for arguments in FINITE_OPTIONS:
                        expected = broken_output(
                            canonical, invocation_link("canonical", applet), applet,
                            arguments, mode, locale,
                        )
                        actual = broken_output(
                            hybrid, invocation_link("hybrid", applet), applet,
                            arguments, mode, locale,
                        )
                        if actual != expected:
                            raise AssertionError((applet, locale, mode, arguments, "broken-output"))
                        checked += 1

    result = {
        "schema": 1,
        "cases": checked,
        "passed": checked,
        "locales": LOCALES,
        "applets": [os.fsdecode(item) for item in [*STATELESS, *FILESYSTEM_CASES, b"yes"]],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
