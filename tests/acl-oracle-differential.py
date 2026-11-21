#!/usr/bin/env python3
"""Compare independent GCC and Clang builds of ACL's public tools."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
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
    modes: dict[str, int] = field(default_factory=dict)
    setup: tuple[tuple[str, tuple[str, ...]], ...] = ()
    stdin: bytes = b""


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
        metadata = path.lstat()
        records.append({
            "path": relative,
            "kind": "directory" if path.is_dir() else "file",
            "mode": stat.S_IMODE(metadata.st_mode),
            "bytes": metadata.st_size if path.is_file() else 0,
            "sha256": digest(path.read_bytes()) if path.is_file() else None,
            "xattrs": attributes,
        })
    return records


def invoke(directory: Path, suffix: str, case: Case) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="rustbox-acl-differential-") as temporary:
        root = Path(temporary)
        for name in case.directories:
            (root / name).mkdir(parents=True, exist_ok=True)
        for name, content in case.files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        for name, mode in case.modes.items():
            (root / name).chmod(mode)
        environment = os.environ.copy()
        environment.update({"LC_ALL": "C", "LANG": "C", "TZ": "UTC"})
        for applet, arguments in case.setup:
            setup = subprocess.run(
                [applet, *arguments], executable=directory / f"{applet}-{suffix}",
                cwd=root, env=environment, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=20,
            )
            if setup.returncode != 0:
                raise RuntimeError(
                    f"setup {applet} {arguments!r} failed: {setup.stderr!r}"
                )
        process = subprocess.run(
            [case.applet, *case.arguments],
            executable=directory / f"{case.applet}-{suffix}", cwd=root,
            env=environment, input=case.stdin, stdout=subprocess.PIPE,
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
    base = {"file": b"payload\n"}
    directory = ("dir",)
    access = "u::rw-,g::r--,o::---,u:12345:r--,m::r--"
    default = "u::rwx,g::r-x,o::---,m::r-x"
    result = [
        Case(f"{applet}-{option[2:]}", applet, (option,))
        for applet in ("getfacl", "setfacl")
        for option in ("--help", "--version")
    ]
    result.extend([
        Case("get-base", "getfacl", ("file",), files=base, modes={"file": 0o640}),
        Case("get-omit-header", "getfacl", ("-c", "file"), files=base),
        Case("get-numeric", "getfacl", ("-n", "file"), files=base),
        Case("get-tabular", "getfacl", ("-t", "file"), files=base),
        Case("get-effective", "getfacl", ("-e", "file"), files=base),
        Case("get-no-effective", "getfacl", ("-E", "file"), files=base,
             setup=(("setfacl", ("-m", "u:12345:rwx,m::r--", "file")),)),
        Case("get-skip-base", "getfacl", ("-s", "file"), files=base),
        Case("get-recursive", "getfacl", ("-R", "tree"),
             files={"tree/a": b"a", "tree/sub/b": b"b"}),
        Case("get-missing", "getfacl", ("missing",)),
        Case("get-stdin-list", "getfacl", ("-",), files=base, stdin=b"file\n"),
        Case("set-modify", "setfacl", ("-m", "u:12345:rw-", "file"), files=base),
        Case("set-numeric-perms", "setfacl", ("-m", "g:12345:5", "file"), files=base),
        Case("set-remove", "setfacl", ("-x", "u:12345", "file"), files=base,
             setup=(("setfacl", ("-m", "u:12345:rw-", "file")),)),
        Case("set-remove-all", "setfacl", ("-b", "file"), files=base,
             setup=(("setfacl", ("-m", "u:12345:rw-", "file")),)),
        Case("set-no-mask", "setfacl", ("-n", "-m", "u:12345:rwx", "file"), files=base),
        Case("set-test", "setfacl", ("--test", "-m", "u:12345:rw-", "file"), files=base),
        Case("set-default", "setfacl", ("-d", "-m", default, "dir"), directories=directory),
        Case("set-remove-default", "setfacl", ("-k", "dir"), directories=directory,
             setup=(("setfacl", ("-d", "-m", default, "dir")),)),
        Case("set-recursive", "setfacl", ("-R", "-m", "u:12345:r--", "tree"),
             files={"tree/a": b"a", "tree/sub/b": b"b"}),
        Case("set-missing", "setfacl", ("-m", "u:12345:r--", "missing")),
        Case("chacl-set", "chacl", (access, "file"), files=base),
        Case("chacl-list", "chacl", ("-l", "file"), files=base,
             setup=(("chacl", (access, "file")),)),
        Case("chacl-remove", "chacl", ("-R", "file"), files=base,
             setup=(("chacl", (access, "file")),)),
        Case("chacl-default", "chacl", ("-d", default, "dir"), directories=directory),
        Case("chacl-both", "chacl", ("-b", access, default, "dir"), directories=directory),
        Case("chacl-invalid", "chacl", ("not-an-acl", "file"), files=base),
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
            raise RuntimeError(f"acl/{case.name}: GCC {gcc} != Clang {clang}")
        records.append({"name": case.name, "applet": case.applet, "result": gcc})
    payload = {"schema": 1, "cases": len(records), "passed": len(records), "records": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"acl canonical differential: {len(records)}/{len(records)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
