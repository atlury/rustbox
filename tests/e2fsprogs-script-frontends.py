#!/usr/bin/env python3
"""Exact CLI and generator comparison for native E2fsprogs script frontends."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


SCRUB_CASES = {
    "e2scrub": [(), ("-V",), ("--help",), ("-h",), ("-n",), ("-r",), ("-A",), ("bogus",)],
    "e2scrub_all": [(), ("-V",), ("--help",), ("-h",), ("-n",), ("-r",), ("-A",), ("bogus",)],
}


def run(executable: Path, name: str, arguments: tuple[str, ...], cwd: Path,
        environment: dict[str, str]) -> tuple[int, bytes, bytes]:
    process = subprocess.run(
        [name, *arguments], executable=executable, cwd=cwd, env=environment,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, timeout=20,
    )
    invoked_path = str(executable).encode()
    stdout = process.stdout.replace(invoked_path, name.encode())
    stderr = process.stderr.replace(invoked_path, name.encode())
    stdout = re.sub(rb"-T [0-9]{14}", b"-T <TIMESTAMP>", stdout)
    stderr = re.sub(rb"-T [0-9]{14}", b"-T <TIMESTAMP>", stderr)
    return (
        process.returncode,
        stdout,
        stderr,
    )


def snapshot(directory: Path) -> list[dict[str, object]]:
    result = []
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        data = path.read_bytes()
        result.append({
            "name": path.name,
            "mode": path.stat().st_mode & 0o7777,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })
    return result


def required_outputs(directory: Path, names: tuple[str, ...]) -> dict[str, tuple[int, bytes]]:
    outputs = {}
    for name in names:
        path = directory / name
        if not path.is_file():
            raise RuntimeError(f"generator did not create required fresh output: {name}")
        outputs[name] = (path.stat().st_mode & 0o7777, path.read_bytes())
    return outputs


def generator_run(executable: Path, name: str, arguments: tuple[str, ...],
                  files: dict[str, bytes], environment: dict[str, str],
                  expected_outputs: tuple[str, ...]) -> tuple[object, object, object]:
    with tempfile.TemporaryDirectory(prefix=f"rustbox-{name}-") as temporary:
        directory = Path(temporary)
        for relative, data in files.items():
            (directory / relative).write_bytes(data)
        outcome = run(executable, name, arguments, directory, environment)
        outputs = required_outputs(directory, expected_outputs)
        return outcome, snapshot(directory), outputs


def repeated_generator_run(
    executable: Path,
    name: str,
    arguments: tuple[str, ...],
    files: dict[str, bytes],
    environment: dict[str, str],
    expected_outputs: tuple[str, ...],
) -> tuple[object, object, bool]:
    with tempfile.TemporaryDirectory(prefix=f"rustbox-{name}-repeat-") as temporary:
        directory = Path(temporary)
        for relative, data in files.items():
            (directory / relative).write_bytes(data)
        first = run(executable, name, arguments, directory, environment)
        if first[0] != 0:
            raise RuntimeError(f"first generator run failed: {name}: {first!r}")
        before = {
            output: (
                (directory / output).stat().st_ino,
                (directory / output).stat().st_mtime_ns,
                (directory / output).stat().st_mode & 0o7777,
                (directory / output).read_bytes(),
            )
            for output in expected_outputs
        }
        second = run(executable, name, arguments, directory, environment)
        outputs = required_outputs(directory, expected_outputs)
        after = {
            output: (
                (directory / output).stat().st_ino,
                (directory / output).stat().st_mtime_ns,
                (directory / output).stat().st_mode & 0o7777,
                (directory / output).read_bytes(),
            )
            for output in expected_outputs
        }
        return second, outputs, before == after


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-root", required=True, type=Path)
    parser.add_argument("--native", required=True, type=Path, action="append")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--lvm-only", action="store_true")
    args = parser.parse_args()

    common = os.environ.copy()
    common.update({"LC_ALL": "C", "LANG": "C", "LANGUAGE": "C"})
    records: list[dict[str, object]] = []

    def check(name: str, label: str, canonical: object, natives: list[object]) -> None:
        passed = all(native == canonical for native in natives)
        records.append({"program": name, "case": label, "passed": passed})
        if not passed:
            raise RuntimeError(f"{name} {label} mismatch: canonical={canonical!r} native={natives!r}")

    scrub_cases = (
        {
            "e2scrub": [("-n", "/mnt/rustbox-e2scrub-test")],
            "e2scrub_all": [("-n",), ("-n", "-A"), ("-n", "-r")],
        }
        if args.lvm_only else SCRUB_CASES
    )
    with tempfile.TemporaryDirectory(prefix="rustbox-e2scrub-cli-") as temporary:
        cwd = Path(temporary)
        for name, cases in scrub_cases.items():
            canonical_path = args.canonical_root / "sbin" / name
            for arguments in cases:
                canonical = run(canonical_path, name, arguments, cwd, common)
                natives = [run(path / name, name, arguments, cwd, common) for path in args.native]
                check(name, "cli:" + " ".join(arguments), canonical, natives)

    if args.lvm_only:
        generator_cases = []
    et_files = {
        "simple.et": (args.source / "lib/et/test_cases/simple.et").read_bytes(),
    }
    ct_files = {
        "test_cmd.ct": (args.source / "lib/ss/test_cmd.ct").read_bytes(),
    }
    canonical_et_env = common | {
        "_ET_DIR_OVERRIDE": str(args.canonical_root / "usr/share/et")
    }
    canonical_ss_env = common | {
        "_SS_DIR_OVERRIDE": str(args.canonical_root / "usr/share/ss")
    }
    native_env = common.copy()
    generator_cases = generator_cases if args.lvm_only else [
        ("compile_et", (), {}, canonical_et_env, ()),
        ("compile_et", ("missing.et",), {}, canonical_et_env, ()),
        ("compile_et", ("simple.et",), et_files, canonical_et_env,
         ("simple.h", "simple.c")),
        ("mk_cmds", (), {}, canonical_ss_env, ()),
        ("mk_cmds", ("missing.ct",), {}, canonical_ss_env, ()),
        ("mk_cmds", ("test_cmd.ct",), ct_files, canonical_ss_env,
         ("test_cmd.c",)),
    ]
    for name, arguments, files, canonical_environment, expected_outputs in generator_cases:
        canonical_path = args.canonical_root / "usr/bin" / name
        canonical = generator_run(
            canonical_path, name, arguments, files, canonical_environment,
            expected_outputs,
        )
        natives = [
            generator_run(
                path / name, name, arguments, files, native_env, expected_outputs
            )
            for path in args.native
        ]
        check(name, "fresh-generator:" + " ".join(arguments), canonical, natives)

    if not args.lvm_only:
        repeat_cases = [
            ("compile_et", ("simple.et",), et_files, canonical_et_env,
             ("simple.h", "simple.c")),
            ("mk_cmds", ("test_cmd.ct",), ct_files, canonical_ss_env,
             ("test_cmd.c",)),
        ]
        for name, arguments, files, canonical_environment, expected_outputs in repeat_cases:
            canonical_path = args.canonical_root / "usr/bin" / name
            canonical = repeated_generator_run(
                canonical_path, name, arguments, files, canonical_environment,
                expected_outputs,
            )
            natives = [
                repeated_generator_run(
                    path / name, name, arguments, files, native_env,
                    expected_outputs,
                )
                for path in args.native
            ]
            check(name, "repeat-preserves-output", canonical, natives)

    result = {
        "schema": 1,
        "release": "1.47.4",
        "programs": 4,
        "cases": len(records),
        "passed": sum(record["passed"] for record in records),
        "native_builds": len(args.native),
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: result[key] for key in ("programs", "cases", "passed")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
