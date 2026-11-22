#!/usr/bin/env python3
"""Exact GCC/Clang contracts for canonical GNU Findutils 4.10.0."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def run(binary: Path, arguments: list[str], *, cwd: Path, stdin: bytes = b"",
        environment: dict[str, str] | None = None) -> dict[str, object]:
    env = os.environ.copy()
    env.update({"LC_ALL": "C", "LANG": "C", "TZ": "UTC0"})
    if environment:
        env.update(environment)
    result = subprocess.run(
        [binary.name, *arguments], executable=binary, cwd=cwd, input=stdin,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    return {
        "status": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def serial(result: dict[str, object]) -> dict[str, object]:
    return {
        "status": result["status"],
        "stdout_bytes": len(result["stdout"]),
        "stdout_sha256": hashlib.sha256(result["stdout"]).hexdigest(),
        "stderr_bytes": len(result["stderr"]),
        "stderr_sha256": hashlib.sha256(result["stderr"]).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gcc-build", type=Path, required=True)
    parser.add_argument("--clang-build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    builds = [args.gcc_build.resolve(), args.clang_build.resolve()]
    records: list[dict[str, object]] = []

    def compare(label: str, relative: str, arguments: list[str], *, cwd: Path,
                stdin: bytes = b"", environments: list[dict[str, str]] | None = None
                ) -> list[dict[str, object]]:
        values = []
        for index, build in enumerate(builds):
            value = run(build / relative, arguments, cwd=cwd, stdin=stdin,
                        environment=(environments or [{}, {}])[index])
            if relative == "locate/updatedb":
                # The kernel supplies a script's executable path as $0 even
                # when subprocess sets a stable argv[0].  Normalize only that
                # diagnostic prefix; all remaining bytes stay exact.
                prefix = os.fsencode(build / relative)
                value["stdout"] = value["stdout"].replace(prefix, b"updatedb")
                value["stderr"] = value["stderr"].replace(prefix, b"updatedb")
            values.append(value)
        passed = values[0] == values[1]
        records.append({"label": label, "utility": Path(relative).name,
                        "arguments": arguments, "passed": passed,
                        "gcc": serial(values[0]), "clang": serial(values[1])})
        if not passed:
            raise RuntimeError(f"Findutils mismatch {label}: {values!r}")
        return values

    with tempfile.TemporaryDirectory(prefix="rustbox-findutils-oracle-") as temporary:
        root = Path(temporary)
        tree = root / "tree"
        (tree / "alpha" / "nested").mkdir(parents=True)
        (tree / "beta").mkdir()
        (tree / "alpha" / "one.txt").write_bytes(b"one\n")
        (tree / "alpha" / "nested" / "TWO.TXT").write_bytes(b"two\n")
        (tree / "beta" / "three.bin").write_bytes(b"\x00\x01\x02")
        (tree / "empty").write_bytes(b"")
        (tree / "alpha" / "link").symlink_to("one.txt")
        for path in tree.rglob("*"):
            if not path.is_symlink():
                os.utime(path, (1_600_000_000, 1_600_000_000))

        for option in (["--help"], ["--version"], ["--definitely-invalid"]):
            compare("find-" + option[0].lstrip("-").replace("-", "_"),
                    "find/find", option, cwd=tree)
        find_cases = [
            ("default", ["."]),
            ("name", [".", "-name", "*.txt"]),
            ("iname", [".", "-iname", "*.txt"]),
            ("type", [".", "-type", "f"]),
            ("depth", [".", "-mindepth", "2", "-maxdepth", "2", "-print"]),
            ("printf", [".", "-type", "f", "-printf", "%P:%s\\n"]),
            ("print0", [".", "-type", "f", "-print0"]),
            ("links", [".", "-type", "l", "-printf", "%P->%l\\n"]),
            ("empty", [".", "-empty", "-print"]),
            ("exec", [".", "-type", "f", "-exec", "/usr/bin/printf", "<%s>\\n", "{}", ";"]),
        ]
        for label, arguments in find_cases:
            compare("find-" + label, "find/find", arguments, cwd=tree)

        for option in (["--help"], ["--version"], ["--definitely-invalid"]):
            compare("xargs-" + option[0].lstrip("-").replace("-", "_"),
                    "xargs/xargs", option, cwd=root)
        xargs_cases = [
            ("basic", ["/usr/bin/printf", "<%s>\\n"], b"alpha\nbeta\n"),
            ("null", ["-0", "/usr/bin/printf", "<%s>\\n"], b"a b\x00c\x00"),
            ("batch", ["-n", "2", "/usr/bin/printf", "[%s][%s]\\n"], b"a b c d\n"),
            ("replace", ["-I", "{}", "/usr/bin/printf", "x{%s}x\\n", "{}"], b"a\nb\n"),
            ("lines", ["-L", "1", "/usr/bin/printf", "<%s>\\n"], b"a b\nc d\n"),
            ("delimiter", ["-d", ":", "/usr/bin/printf", "<%s>\\n"], b"a:b c:d"),
            ("empty", ["-r", "/usr/bin/printf", "unexpected"], b""),
        ]
        for label, arguments, stdin in xargs_cases:
            compare("xargs-" + label, "xargs/xargs", arguments, cwd=root, stdin=stdin)

        names = sorted(os.fsencode(str(path)) for path in tree.rglob("*"))
        databases = [root / "gcc.db", root / "clang.db"]
        for index, build in enumerate(builds):
            result = subprocess.run(
                [build / "locate/frcode", "-0"], input=b"\0".join(names) + b"\0",
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env={**os.environ, "LC_ALL": "C"},
            )
            if result.returncode != 0:
                raise RuntimeError(f"frcode failed: {result.stderr!r}")
            databases[index].write_bytes(result.stdout)
        if databases[0].read_bytes() != databases[1].read_bytes():
            raise RuntimeError("GCC and Clang frcode databases differ")
        records.append({"label": "frcode-database", "utility": "frcode",
                        "arguments": ["-0"], "passed": True,
                        "bytes": databases[0].stat().st_size,
                        "sha256": hashlib.sha256(databases[0].read_bytes()).hexdigest()})

        locate_envs = [{"LOCATE_PATH": str(database)} for database in databases]
        for option in (["--help"], ["--version"], ["--definitely-invalid"]):
            compare("locate-" + option[0].lstrip("-").replace("-", "_"),
                    "locate/locate", option, cwd=root, environments=locate_envs)
        for label, arguments in [
            ("name", ["one.txt"]), ("ignore-case", ["-i", "two.txt"]),
            ("basename", ["-b", "three.bin"]), ("regex", ["--regex", ".*\\.txt$"]),
            ("count", ["-c", "txt"]), ("limit", ["-l", "1", "txt"]),
            ("missing", ["not-present-anywhere"]),
        ]:
            compare("locate-" + label, "locate/locate", arguments, cwd=root,
                    environments=locate_envs)

        updated_databases = [root / "updated-gcc.db", root / "updated-clang.db"]
        for index, build in enumerate(builds):
            environment = {
                "find": str(build / "find/find"),
                "frcode": str(build / "locate/frcode"),
            }
            result = run(
                build / "locate/updatedb",
                [f"--localpaths={tree}", "--netpaths=", "--prunepaths=",
                 "--prunefs=", f"--output={updated_databases[index]}",
                 f"--changecwd={root}"],
                cwd=root, environment=environment,
            )
            if result["status"] != 0:
                raise RuntimeError(f"updatedb failed: {result!r}")
        if updated_databases[0].read_bytes() != updated_databases[1].read_bytes():
            raise RuntimeError("GCC and Clang updatedb databases differ")
        records.append({"label": "updatedb-functional", "utility": "updatedb",
                        "arguments": ["--localpaths", "--output"], "passed": True,
                        "bytes": updated_databases[0].stat().st_size,
                        "sha256": hashlib.sha256(updated_databases[0].read_bytes()).hexdigest()})
        for option in (["--help"], ["--version"], ["--definitely-invalid"]):
            compare("updatedb-" + option[0].lstrip("-").replace("-", "_"),
                    "locate/updatedb", option, cwd=root)

    output = {"schema": 1, "release": "4.10.0", "cases": len(records),
              "passed": sum(bool(record["passed"]) for record in records),
              "results": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"cases": output["cases"], "passed": output["passed"]},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
