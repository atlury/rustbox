#!/usr/bin/env python3
"""Compiler-independent contracts for GNU tar 1.35 and GNU rmt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(binary: Path, arguments: list[str], *, cwd: Path | None = None,
        stdin: bytes = b"") -> dict[str, object]:
    environment = os.environ.copy()
    environment.update({"LC_ALL": "C", "LANG": "C", "TZ": "UTC0"})
    result = subprocess.run(
        [binary.name, *arguments], executable=str(binary), cwd=cwd, input=stdin,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment,
    )
    return {"status": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def serial(value: dict[str, object]) -> dict[str, object]:
    return {
        "status": value["status"],
        "stdout_bytes": len(value["stdout"]),
        "stdout_sha256": digest(value["stdout"]),
        "stderr_bytes": len(value["stderr"]),
        "stderr_sha256": digest(value["stderr"]),
    }


def tree(root: Path) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        info = path.lstat()
        record: dict[str, object] = {
            "path": path.relative_to(root).as_posix(),
            "mode": stat.S_IMODE(info.st_mode),
        }
        if path.is_symlink():
            record.update({"kind": "symlink", "target": os.readlink(path)})
        elif path.is_dir():
            record["kind"] = "directory"
        elif path.is_file():
            record.update({"kind": "file", "bytes": info.st_size,
                           "sha256": digest(path.read_bytes())})
        else:
            record["kind"] = "other"
        result.append(record)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gcc-root", required=True, type=Path)
    parser.add_argument("--clang-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    pairs = {
        "tar": (args.gcc_root / "usr/bin/tar", args.clang_root / "usr/bin/tar"),
        "rmt": (args.gcc_root / "usr/libexec/rmt", args.clang_root / "usr/libexec/rmt"),
    }
    cases: list[dict[str, object]] = []

    def compare(label: str, name: str, arguments: list[str], *, cwd: Path | None = None,
                stdin: bytes = b"") -> tuple[dict[str, object], dict[str, object]]:
        left = run(pairs[name][0], arguments, cwd=cwd, stdin=stdin)
        right = run(pairs[name][1], arguments, cwd=cwd, stdin=stdin)
        passed = left == right
        cases.append({"label": label, "name": name, "arguments": arguments,
                      "passed": passed, "gcc": serial(left), "clang": serial(right)})
        if not passed:
            raise RuntimeError(f"GNU tar compiler differential mismatch: {label}")
        return left, right

    compare("tar-help", "tar", ["--help"])
    compare("tar-version", "tar", ["--version"])
    compare("tar-missing-file", "tar", ["-tf", "does-not-exist.tar"])
    compare("tar-conflicting-operation", "tar", ["-cxtf", "archive.tar"])
    compare("rmt-empty-protocol", "rmt", [], stdin=b"")
    compare("rmt-invalid-command", "rmt", [], stdin=b"X\n")

    with tempfile.TemporaryDirectory(prefix="rustbox-tar-differential-") as temporary:
        work = Path(temporary)
        source = work / "source"
        source.mkdir()
        (source / "alpha.txt").write_bytes(b"alpha\n" * 1024)
        (source / "empty").write_bytes(b"")
        nested = source / "nested"
        nested.mkdir(mode=0o750)
        payload = bytes(range(256)) * 16
        (nested / "payload.bin").write_bytes(payload)
        os.link(source / "alpha.txt", source / "alpha-hardlink")
        os.symlink("nested/payload.bin", source / "payload-link")

        common = [
            "--format=ustar", "--sort=name", "--owner=0", "--group=0",
            "--numeric-owner", "--mtime=@0", "-cf", "-", "-C", str(source), ".",
        ]
        streams = [run(binary, common) for binary in pairs["tar"]]
        if streams[0] != streams[1] or streams[0]["status"] != 0:
            raise RuntimeError("GNU tar deterministic archive creation differs")
        archive = streams[0]["stdout"]
        cases.append({
            "label": "tar-create-deterministic", "name": "tar", "arguments": common,
            "passed": True, "gcc": serial(streams[0]), "clang": serial(streams[1]),
            "byte_identical_archive": True,
        })
        archive_path = work / "archive.tar"
        archive_path.write_bytes(archive)

        compare("tar-list", "tar", ["-tf", str(archive_path)])
        compare("tar-list-verbose", "tar", ["--numeric-owner", "-tvf", str(archive_path)])
        compare("tar-list-stdin", "tar", ["-tf", "-"], stdin=archive)
        compare("tar-test-label-failure", "tar", ["--test-label", "-f", str(archive_path)])

        extracted: list[list[dict[str, object]]] = []
        for compiler, binary in zip(("gcc", "clang"), pairs["tar"]):
            destination = work / f"extract-{compiler}"
            destination.mkdir()
            result = run(binary, ["-xf", str(archive_path), "-C", str(destination)])
            if result["status"] != 0:
                raise RuntimeError(f"GNU tar {compiler} extraction failed")
            extracted.append(tree(destination))
        if extracted[0] != extracted[1]:
            raise RuntimeError("GNU tar extracted filesystem trees differ")
        cases.append({"label": "tar-extract-tree", "name": "tar", "arguments": ["-xf"],
                      "passed": True, "filesystem_entries": len(extracted[0])})

        for option, suffix in (("--gzip", "gz"), ("--xz", "xz"), ("--zstd", "zst")):
            outputs = [run(binary, [option, "-cf", "-", "-C", str(source), "."])
                       for binary in pairs["tar"]]
            passed = outputs[0] == outputs[1] and outputs[0]["status"] == 0
            cases.append({"label": f"tar-create-{suffix}", "name": "tar",
                          "arguments": [option], "passed": passed,
                          "gcc": serial(outputs[0]), "clang": serial(outputs[1])})
            if not passed:
                raise RuntimeError(f"GNU tar {suffix} compressor personality differs")
            compare(f"tar-list-{suffix}", "tar", ["-tf", "-"], stdin=outputs[0]["stdout"])

    output = {
        "schema": 1,
        "release": "1.35",
        "public_names": ["tar", "rmt"],
        "cases": len(cases),
        "passed": sum(case["passed"] for case in cases),
        "results": cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"cases": output["cases"], "passed": output["passed"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
