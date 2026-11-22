#!/usr/bin/env python3
"""Compiler-independent contracts for the installed Ncurses 6.6 utilities."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path


NAMES = [
    "captoinfo", "clear", "infocmp", "infotocap", "tabs", "tic", "toe",
    "tput", "tset", "reset", "ncursesw6-config",
]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(root: Path, name: str, arguments: list[str], *, stdin: bytes = b"",
        cwd: Path | None = None, extra_environment: dict[str, str] | None = None
        ) -> dict[str, object]:
    binary = root / "usr/bin" / name
    environment = os.environ.copy()
    environment.update({
        "LC_ALL": "C", "LANG": "C", "TERM": "xterm", "TZ": "UTC0",
        "TERMINFO": str(root / "usr/share/terminfo"),
        "TERMINFO_DIRS": str(root / "usr/share/terminfo"),
        "LD_LIBRARY_PATH": str(root / "usr/lib"),
    })
    if extra_environment:
        environment.update(extra_environment)
    result = subprocess.run(
        [name, *arguments], executable=str(binary), cwd=cwd, input=stdin,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment,
    )
    return {"status": result.returncode, "stdout": result.stdout,
            "stderr": result.stderr}


def serial(value: dict[str, object]) -> dict[str, object]:
    return {
        "status": value["status"],
        "stdout_bytes": len(value["stdout"]),
        "stdout_sha256": digest(value["stdout"]),
        "stderr_bytes": len(value["stderr"]),
        "stderr_sha256": digest(value["stderr"]),
    }


def tree(root: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
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
        records.append(record)
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gcc-root", required=True, type=Path)
    parser.add_argument("--clang-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    roots = [args.gcc_root, args.clang_root]
    cases: list[dict[str, object]] = []

    def compare(label: str, name: str, arguments: list[str], *, stdin: bytes = b"",
                cwd: Path | None = None,
                extra_environment: dict[str, str] | None = None
                ) -> tuple[dict[str, object], dict[str, object]]:
        values = [run(root, name, arguments, stdin=stdin, cwd=cwd,
                      extra_environment=extra_environment) for root in roots]
        passed = values[0] == values[1]
        cases.append({"label": label, "name": name, "arguments": arguments,
                      "passed": passed, "gcc": serial(values[0]),
                      "clang": serial(values[1])})
        if not passed:
            raise RuntimeError(
                f"Ncurses compiler differential mismatch: {label}: "
                f"gcc={serial(values[0])}, clang={serial(values[1])}, "
                f"gcc_stdout={values[0]['stdout']!r}, "
                f"clang_stdout={values[1]['stdout']!r}, "
                f"gcc_stderr={values[0]['stderr']!r}, "
                f"clang_stderr={values[1]['stderr']!r}"
            )
        return values[0], values[1]

    for name in NAMES[:-1]:
        compare(f"{name}-version", name, ["-V"])
    for option in ("--version", "--cflags", "--libs", "--terminfo", "--terminfo-dirs"):
        compare(f"ncursesw6-config-{option[2:]}", "ncursesw6-config", [option])

    compare("tput-cols", "tput", ["cols"])
    compare("tput-lines", "tput", ["lines"])
    compare("tput-clear", "tput", ["clear"])
    compare("clear-xterm", "clear", [])
    compare("tabs-every-eight", "tabs", ["-8"])
    compare("tset-invalid-terminal", "tset", ["-Q"],
            extra_environment={"TERM": "rustbox-missing-terminal"})
    compare("reset-invalid-terminal", "reset", ["-Q"],
            extra_environment={"TERM": "rustbox-missing-terminal"})

    source = b"""rustbox-demo|deterministic Rustbox terminal,\n\tam, cols#80, lines#24,\n\tclear=\\E[H\\E[2J, bel=^G, cr=^M, cud1=^J,\n"""
    with tempfile.TemporaryDirectory(prefix="rustbox-ncurses-oracle-") as temporary:
        base = Path(temporary)
        source_path = base / "demo.src"
        source_path.write_bytes(source)
        database_trees: list[list[dict[str, object]]] = []
        database_paths: list[Path] = []
        for compiler, root in zip(("gcc", "clang"), roots):
            database = base / f"database-{compiler}"
            database.mkdir()
            result = run(root, "tic", ["-x", "-o", str(database), str(source_path)])
            if result["status"] != 0:
                raise RuntimeError(f"Ncurses {compiler} tic compilation failed: {result!r}")
            database_paths.append(database)
            database_trees.append(tree(database))
        if database_trees[0] != database_trees[1]:
            raise RuntimeError("Ncurses GCC and Clang terminfo databases differ")
        cases.append({"label": "tic-compile-database", "name": "tic",
                      "arguments": ["-x", "-o"], "passed": True,
                      "filesystem_entries": len(database_trees[0])})

        for name, arguments in (
            ("infocmp", ["-A", str(database_paths[0]), "rustbox-demo"]),
            ("captoinfo", [str(source_path)]),
            ("infotocap", [str(source_path)]),
        ):
            # Use the same compiler-independent input path for both binaries.
            compare(f"{name}-custom-entry", name, arguments)

        values = [run(root, "toe", ["-a"],
                      extra_environment={"TERMINFO": str(database)})
                  for root, database in zip(roots, database_paths)]
        normalized = [value["stdout"].replace(str(database_paths[index]).encode(), b"DATABASE")
                      for index, value in enumerate(values)]
        passed = (values[0]["status"], normalized[0], values[0]["stderr"]) == (
            values[1]["status"], normalized[1], values[1]["stderr"])
        cases.append({"label": "toe-custom-database", "name": "toe",
                      "arguments": ["-a"], "passed": passed,
                      "gcc": serial(values[0]), "clang": serial(values[1])})
        if not passed:
            raise RuntimeError("Ncurses toe custom-database output differs")

    output = {
        "schema": 1,
        "release": "6.6",
        "public_names": NAMES,
        "cases": len(cases),
        "passed": sum(bool(case["passed"]) for case in cases),
        "results": cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"cases": output["cases"], "passed": output["passed"]},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
