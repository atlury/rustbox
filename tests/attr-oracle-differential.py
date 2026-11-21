#!/usr/bin/env python3
"""Compare independent GCC and Clang builds of attr's three public tools."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Case:
    name: str
    applet: str
    arguments: tuple[str, ...]
    files: dict[str, bytes] = field(default_factory=dict)
    directories: tuple[str, ...] = ()
    setup: tuple[tuple[str, tuple[str, ...]], ...] = ()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot(root: Path) -> list[dict[str, object]]:
    records = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        attributes = []
        for name in sorted(os.listxattr(path, follow_symlinks=False)):
            value = os.getxattr(path, name, follow_symlinks=False)
            attributes.append([name, len(value), digest(value)])
        records.append({
            "path": relative,
            "kind": "directory" if path.is_dir() else "file",
            "bytes": path.stat().st_size if path.is_file() else 0,
            "sha256": digest(path.read_bytes()) if path.is_file() else None,
            "xattrs": attributes,
        })
    return records


def invoke(directory: Path, suffix: str, case: Case) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="rustbox-attr-differential-") as temporary:
        root = Path(temporary)
        for name in case.directories:
            (root / name).mkdir(parents=True, exist_ok=True)
        for name, content in case.files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        environment = os.environ.copy()
        environment.update({"LC_ALL": "C", "LANG": "C", "TZ": "UTC"})
        for applet, arguments in case.setup:
            setup = subprocess.run(
                [applet, *arguments], executable=directory / f"{applet}-{suffix}", cwd=root,
                env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=20,
            )
            if setup.returncode != 0:
                raise RuntimeError(
                    f"setup {applet} {arguments!r} failed: {setup.stderr!r}"
                )
        process = subprocess.run(
            [case.applet, *case.arguments], executable=directory / f"{case.applet}-{suffix}",
            cwd=root, env=environment, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=20,
        )
        return {
            "status": process.returncode,
            "stdout_sha256": digest(process.stdout),
            "stdout_length": len(process.stdout),
            "stderr_sha256": digest(process.stderr),
            "stderr_length": len(process.stderr),
            "tree": snapshot(root),
        }


def cases() -> list[Case]:
    result = [
        Case(f"{applet}-{option[2:]}", applet, (option,))
        for applet in ("attr", "getfattr", "setfattr")
        for option in ("--help", "--version")
    ]
    result.extend([
        Case("set-text", "setfattr", ("-n", "user.name", "-v", "value", "file"), files={"file": b"payload"}),
        Case("set-hex", "setfattr", ("-n", "user.bytes", "-v", "0x00ff10", "file"), files={"file": b""}),
        Case("set-base64", "setfattr", ("-n", "user.bytes", "-v", "0sAP8Q", "file"), files={"file": b""}),
        Case("remove", "setfattr", ("-x", "user.name", "file"), files={"file": b""}, setup=(("setfattr", ("-n", "user.name", "-v", "value", "file")),)),
        Case("set-missing", "setfattr", ("-n", "user.name", "-v", "value", "missing")),
        Case("get-name", "getfattr", ("-n", "user.name", "file"), files={"file": b""}, setup=(("setfattr", ("-n", "user.name", "-v", "value", "file")),)),
        Case("get-dump", "getfattr", ("-d", "file"), files={"file": b""}, setup=(("setfattr", ("-n", "user.alpha", "-v", "one", "file")), ("setfattr", ("-n", "user.beta", "-v", "two", "file")))),
        Case("get-only-values", "getfattr", ("--only-values", "-n", "user.name", "file"), files={"file": b""}, setup=(("setfattr", ("-n", "user.name", "-v", "value", "file")),)),
        Case("get-hex", "getfattr", ("-d", "-e", "hex", "file"), files={"file": b""}, setup=(("setfattr", ("-n", "user.bytes", "-v", "0x00ff10", "file")),)),
        Case("get-base64", "getfattr", ("-d", "-e", "base64", "file"), files={"file": b""}, setup=(("setfattr", ("-n", "user.bytes", "-v", "0x00ff10", "file")),)),
        Case("get-recursive", "getfattr", ("-R", "-d", "tree"), files={"tree/a": b"a", "tree/sub/b": b"b"}, setup=(("setfattr", ("-n", "user.one", "-v", "1", "tree/a")), ("setfattr", ("-n", "user.two", "-v", "2", "tree/sub/b")))),
        Case("get-missing", "getfattr", ("-n", "user.name", "missing")),
        Case("attr-set", "attr", ("-s", "rustbox", "-V", "value", "file"), files={"file": b""}),
        Case("attr-get", "attr", ("-g", "rustbox", "file"), files={"file": b""}, setup=(("attr", ("-s", "rustbox", "-V", "value", "file")),)),
        Case("attr-list", "attr", ("-l", "file"), files={"file": b""}, setup=(("attr", ("-s", "alpha", "-V", "one", "file")), ("attr", ("-s", "beta", "-V", "two", "file")))),
        Case("attr-remove", "attr", ("-r", "rustbox", "file"), files={"file": b""}, setup=(("attr", ("-s", "rustbox", "-V", "value", "file")),)),
    ])
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gcc-directory", type=Path, required=True)
    parser.add_argument("--clang-directory", type=Path, required=True)
    parser.add_argument("--gcc-suffix", default="gcc")
    parser.add_argument("--clang-suffix", default="clang")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = []
    for case in cases():
        gcc = invoke(args.gcc_directory, args.gcc_suffix, case)
        clang = invoke(args.clang_directory, args.clang_suffix, case)
        if gcc != clang:
            raise RuntimeError(f"attr/{case.name}: GCC {gcc} != Clang {clang}")
        records.append({"name": case.name, "applet": case.applet, "result": gcc})
    payload = {"schema": 1, "cases": len(records), "passed": len(records), "records": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"attr canonical differential: {len(records)}/{len(records)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
