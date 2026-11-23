#!/usr/bin/env python3
"""0BSD. Compare independent canonical Bison builds and generated parsers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


CALC_INPUT = b"1 + 2 * 3\n(8 - 2) / 3\n"
GLR_INPUT = b"T x;\nT (x) = y;\n"
YACC_INPUT = b"1\n7\n"


@dataclass(frozen=True)
class Case:
    name: str
    source: str
    arguments: tuple[str, ...]
    contents: bytes | None = None
    compile_source: str | None = None
    compiler: str = "gcc"
    runtime_input: bytes = b""
    extra_sources: tuple[str, ...] = ()


CASES = (
    Case(
        "c-pull",
        "examples/c/calc/calc.y",
        ("--defines=calc.h", "--report=all", "--output=calc.c"),
        compile_source="calc.c",
        runtime_input=CALC_INPUT,
    ),
    Case(
        "c-push",
        "examples/c/pushcalc/calc.y",
        ("--defines=calc.h", "--report=all", "--output=calc.c"),
        compile_source="calc.c",
        runtime_input=CALC_INPUT,
    ),
    Case(
        "c-glr",
        "examples/c/glr/c++-types.y",
        ("--defines=c++-types.h", "--output=c++-types.c"),
        compile_source="c++-types.c",
        runtime_input=GLR_INPUT,
    ),
    Case(
        "cxx-lalr",
        "examples/c++/simple.yy",
        ("--output=simple.cc",),
        compile_source="simple.cc",
        compiler="g++",
    ),
    Case(
        "cxx-glr",
        "examples/c++/glr/c++-types.yy",
        ("--defines=c++-types.hh", "--output=c++-types.cc"),
        extra_sources=("examples/c++/glr/ast.hh",),
    ),
    Case(
        "cxx-glr2",
        "examples/c++/glr/c++-types.yy",
        ("--skeleton=glr2.cc", "--defines=c++-types.hh", "--output=c++-types.cc"),
        extra_sources=("examples/c++/glr/ast.hh",),
    ),
    Case(
        "yacc-compatible",
        "yacc.y",
        ("--yacc", "--defines",),
        contents=br"""%{
#include <ctype.h>
#include <stdio.h>
int yylex (void);
void yyerror (const char *message);
%}
%token NUM
%%
input: %empty | input line;
line: '\n' | NUM '\n' { printf ("%d\n", $1); };
%%
int yylex (void) {
  int c = getchar ();
  if (isdigit (c)) { yylval = c - '0'; return NUM; }
  return c == EOF ? 0 : c;
}
void yyerror (const char *message) { fprintf (stderr, "%s\n", message); }
int main (void) { return yyparse (); }
""",
        compile_source="y.tab.c",
        runtime_input=YACC_INPUT,
    ),
    Case(
        "reports",
        "examples/c/calc/calc.y",
        ("--defines=calc.h", "--xml=calc.xml", "--graph=calc.dot",
         "--report=all", "--output=calc.c"),
    ),
)


def run(command: list[str], *, cwd: Path, environment: dict[str, str] | None = None,
        input_bytes: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command, cwd=cwd, env=environment, input=input_bytes,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def manifest(directory: Path, inputs: set[str]) -> dict[str, bytes]:
    return {
        str(path.relative_to(directory)): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file() and str(path.relative_to(directory)) not in inputs
        and path.name != "parser"
    }


def bison_environment(datadir: Path | None) -> dict[str, str]:
    environment = dict(os.environ)
    if datadir is None:
        environment.pop("BISON_PKGDATADIR", None)
        environment.pop("M4", None)
    else:
        environment["BISON_PKGDATADIR"] = str(datadir)
    return environment


def exercise(binary: Path, datadir: Path | None, source_root: Path,
             case: Case) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix=f"rustbox-bison-{case.name}-") as raw:
        directory = Path(raw)
        source_name = Path(case.source).name
        if case.contents is None:
            shutil.copyfile(source_root / case.source, directory / source_name)
        else:
            (directory / source_name).write_bytes(case.contents)
        copied = {source_name}
        for item in case.extra_sources:
            name = Path(item).name
            shutil.copyfile(source_root / item, directory / name)
            copied.add(name)
        generated = run(
            [str(binary), *case.arguments, source_name],
            cwd=directory, environment=bison_environment(datadir),
        )
        files = manifest(directory, copied)
        runtime: subprocess.CompletedProcess[bytes] | None = None
        compile_result: subprocess.CompletedProcess[bytes] | None = None
        if generated.returncode == 0 and case.compile_source:
            executable = directory / "parser"
            compile_result = run(
                [case.compiler, "-O2", "-std=c++17" if case.compiler == "g++" else "-std=gnu11",
                 case.compile_source, "-o", str(executable)],
                cwd=directory,
            )
            if compile_result.returncode == 0:
                runtime = run([str(executable)], cwd=directory, input_bytes=case.runtime_input)
        return {
            "status": generated.returncode,
            "stdout": generated.stdout,
            "stderr": generated.stderr,
            "manifest": files,
            "compile_status": None if compile_result is None else compile_result.returncode,
            "compile_stdout": b"" if compile_result is None else compile_result.stdout,
            "compile_stderr": b"" if compile_result is None else compile_result.stderr,
            "runtime_status": None if runtime is None else runtime.returncode,
            "runtime_stdout": b"" if runtime is None else runtime.stdout,
            "runtime_stderr": b"" if runtime is None else runtime.stderr,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gcc", type=Path, required=True)
    parser.add_argument("--gcc-datadir", type=Path, required=True)
    parser.add_argument("--clang", type=Path, required=True)
    parser.add_argument("--clang-datadir", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--right-embedded", action="store_true",
        help="run the clang/right binary with no external Bison datadir or M4",
    )
    args = parser.parse_args()
    right_datadir = None if args.right_embedded else args.clang_datadir
    resource_directories_before = set(Path("/tmp").glob("rustbox-bison.*"))

    records: list[dict[str, object]] = []
    for name, options, stdin in (
        ("version", ("--version",), None),
        ("help", ("--help",), None),
        ("invalid-option", ("--definitely-invalid",), None),
        ("malformed-stdin", (), b"%%\nstart: [ ;\n%%\n"),
    ):
        values = []
        for binary, datadir in (
            (args.gcc, args.gcc_datadir), (args.clang, right_datadir),
        ):
            with tempfile.TemporaryDirectory(prefix=f"rustbox-bison-cli-{name}-") as raw:
                directory = Path(raw)
                os.symlink(binary, directory / "bison")
                values.append(run(
                    ["./bison", *options], cwd=directory,
                    environment=bison_environment(datadir),
                    input_bytes=stdin,
                ))
        left, right = values
        if (left.returncode, left.stdout, left.stderr) != (
            right.returncode, right.stdout, right.stderr
        ):
            raise RuntimeError(f"Bison compiler CLI mismatch: {name}")
        records.append({
            "name": name,
            "kind": "cli",
            "passed": True,
            "status": left.returncode,
            "stdout_sha256": digest(left.stdout),
            "stderr_sha256": digest(left.stderr),
        })

    for case in CASES:
        left = exercise(args.gcc, args.gcc_datadir, args.source, case)
        right = exercise(args.clang, right_datadir, args.source, case)
        if left != right:
            raise RuntimeError(f"Bison generated-parser mismatch: {case.name}")
        if left["status"] != 0:
            raise RuntimeError(
                f"Bison generation failed: {case.name}: status={left['status']}\n"
                + bytes(left["stderr"]).decode(errors="replace")
            )
        if case.compile_source and (
            left["compile_status"] != 0 or left["runtime_status"] != 0
        ):
            raise RuntimeError(
                f"Bison generated parser failed: {case.name}: "
                f"compile={left['compile_status']} runtime={left['runtime_status']}\n"
                + bytes(left["compile_stderr"]).decode(errors="replace")
                + bytes(left["runtime_stderr"]).decode(errors="replace")
            )
        files = left["manifest"]
        assert isinstance(files, dict)
        records.append({
            "name": case.name,
            "kind": "generated-parser",
            "passed": True,
            "generated_files": sorted(files),
            "generated_sha256": {
                name: digest(data) for name, data in sorted(files.items())
            },
            "runtime_status": left["runtime_status"],
            "runtime_stdout_sha256": digest(left["runtime_stdout"]),
            "runtime_stderr_sha256": digest(left["runtime_stderr"]),
        })

    leaked_resource_directories = sorted(
        str(path) for path in set(Path("/tmp").glob("rustbox-bison.*"))
        - resource_directories_before
    )
    if leaked_resource_directories:
        raise RuntimeError(
            "embedded Bison resource directories were not cleaned: "
            + ", ".join(leaked_resource_directories)
        )
    evidence = {
        "schema": 1,
        "cases": len(records),
        "passed": sum(record["passed"] is True for record in records),
        "compiled_parsers": sum(case.compile_source is not None for case in CASES),
        "right_embedded": args.right_embedded,
        "resource_directories_leaked": 0,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        key: evidence[key] for key in ("cases", "passed", "compiled_parsers")
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
