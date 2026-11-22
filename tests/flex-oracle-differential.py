#!/usr/bin/env python3
"""0BSD. Compare independently compiled canonical Flex generators and scanners."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


INPUT = b"alpha 12 + beta\n34\n"

C_SPEC = br"""%option noyywrap nodefault
%{
#include <stdio.h>
%}
%%
[0-9]+       { printf("N:%s\n", yytext); }
[A-Za-z]+    { printf("W:%s\n", yytext); }
[ \t\r\n]+   ;
.             { printf("P:%s\n", yytext); }
%%
int main(void) { return yylex(); }
"""

REENTRANT_SPEC = br"""%option reentrant noyywrap nodefault
%{
#include <stdio.h>
%}
%%
[0-9]+       { printf("N:%s\n", yytext); }
[A-Za-z]+    { printf("W:%s\n", yytext); }
[ \t\r\n]+   ;
.             { printf("P:%s\n", yytext); }
%%
int main(void) {
    yyscan_t scanner;
    if (yylex_init(&scanner) != 0) return 2;
    int status = yylex(scanner);
    yylex_destroy(scanner);
    return status;
}
"""

PREFIX_SPEC = br"""%option noyywrap nodefault
%{
#include <stdio.h>
%}
%%
[0-9]+       { printf("N:%s\n", yytext); }
[A-Za-z]+    { printf("W:%s\n", yytext); }
[ \t\r\n]+   ;
.             { printf("P:%s\n", yytext); }
%%
int main(void) { return foolex(); }
"""

CXX_SPEC = br"""%option c++ noyywrap nodefault
%{
#include <iostream>
%}
%%
[0-9]+       { std::cout << "N:" << YYText() << '\n'; }
[A-Za-z]+    { std::cout << "W:" << YYText() << '\n'; }
[ \t\r\n]+   ;
.             { std::cout << "P:" << YYText() << '\n'; }
%%
int main() { yyFlexLexer scanner; return scanner.yylex(); }
"""


@dataclass(frozen=True)
class GenerationCase:
    name: str
    arguments: tuple[str, ...]
    source: bytes = C_SPEC
    cxx: bool = False
    stdout_source: bool = False


CASES = (
    GenerationCase("default-c", ()),
    GenerationCase("full-table", ("-Cf",)),
    GenerationCase("fast-table", ("-CF",)),
    GenerationCase("compressed-meta", ("-Cem",)),
    GenerationCase("lex-compat", ("-l",)),
    GenerationCase("reentrant", (), REENTRANT_SPEC),
    GenerationCase("prefix", ("-Pfoo",), PREFIX_SPEC),
    GenerationCase("explicit-output-header", ("-o", "scanner.c", "--header-file=scanner.h")),
    GenerationCase("stdout", ("-t",), stdout_source=True),
    GenerationCase("cxx", ("-+",), CXX_SPEC, cxx=True),
)


def completed(command: list[str], *, cwd: Path | None = None,
              input_bytes: bytes | None = None) -> dict[str, object]:
    result = subprocess.run(
        command, cwd=cwd, input=input_bytes, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
    )
    return {
        "status": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def file_manifest(directory: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(directory)): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.name != "scanner.l"
    }


def generated_source(manifest: dict[str, bytes], case: GenerationCase,
                     stdout: bytes) -> tuple[str, bytes]:
    if case.stdout_source:
        return ("scanner.cc" if case.cxx else "scanner.c", stdout)
    suffix = ".cc" if case.cxx else ".c"
    candidates = [(name, data) for name, data in manifest.items()
                  if name.endswith(suffix)]
    if len(candidates) != 1:
        raise RuntimeError(f"{case.name}: generated sources {sorted(manifest)}")
    return candidates[0]


def run_generation(binary: Path, case: GenerationCase, source_root: Path,
                   compiler: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix=f"rustbox-flex-{case.name}-") as raw:
        directory = Path(raw)
        (directory / "scanner.l").write_bytes(case.source)
        result = completed([str(binary), *case.arguments, "scanner.l"], cwd=directory)
        manifest = file_manifest(directory)
        if result["status"] != 0:
            return {**result, "manifest": manifest, "runtime": None}
        source_name, source = generated_source(
            manifest, case, result["stdout"]  # type: ignore[arg-type]
        )
        generated = directory / ("compiled.cc" if case.cxx else "compiled.c")
        generated.write_bytes(source)
        executable = directory / "scanner"
        driver = "g++" if case.cxx else "gcc"
        compile_result = completed([
            driver, "-O2", "-I", str(source_root / "src"), str(generated),
            "-o", str(executable),
        ], cwd=directory)
        if compile_result["status"] != 0:
            raise RuntimeError(
                f"{compiler}/{case.name}: generated scanner did not compile:\n"
                + compile_result["stderr"].decode(errors="replace")  # type: ignore[union-attr]
            )
        runtime = completed([str(executable)], cwd=directory, input_bytes=INPUT)
        # The compiled artifact is deliberately outside the generator manifest.
        return {**result, "manifest": manifest, "runtime": runtime,
                "source_name": source_name}


def comparable(value: dict[str, object]) -> dict[str, object]:
    return {
        "status": value["status"],
        "stdout": value["stdout"],
        "stderr": value["stderr"],
        "manifest": value.get("manifest"),
        "runtime": value.get("runtime"),
        "source_name": value.get("source_name"),
    }


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gcc", type=Path, required=True)
    parser.add_argument("--clang", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    records: list[dict[str, object]] = []
    cli_cases = (
        ("version", ("--version",), None),
        ("help", ("--help",), None),
        ("invalid-option", ("--definitely-invalid",), None),
        ("malformed-spec", (), b"%%\n[ unclosed\n"),
    )
    for name, arguments, stdin in cli_cases:
        with tempfile.TemporaryDirectory(prefix=f"rustbox-flex-cli-gcc-{name}-") as left_dir:
            os.symlink(args.gcc, Path(left_dir) / "flex")
            left = completed(["./flex", *arguments], cwd=Path(left_dir),
                             input_bytes=stdin)
        with tempfile.TemporaryDirectory(prefix=f"rustbox-flex-cli-clang-{name}-") as right_dir:
            os.symlink(args.clang, Path(right_dir) / "flex")
            right = completed(["./flex", *arguments], cwd=Path(right_dir),
                              input_bytes=stdin)
        passed = left == right
        if not passed:
            raise RuntimeError(f"Flex compiler CLI mismatch: {name}")
        records.append({
            "name": name, "kind": "cli", "passed": True,
            "status": left["status"],
            "stdout_sha256": digest_bytes(left["stdout"]),  # type: ignore[arg-type]
            "stderr_sha256": digest_bytes(left["stderr"]),  # type: ignore[arg-type]
        })

    for case in CASES:
        left = run_generation(args.gcc, case, args.source, "gcc")
        right = run_generation(args.clang, case, args.source, "clang")
        passed = comparable(left) == comparable(right)
        if not passed:
            raise RuntimeError(f"Flex generated-scanner mismatch: {case.name}")
        runtime = left["runtime"]
        if not isinstance(runtime, dict) or runtime["status"] != 0:
            raise RuntimeError(f"Flex generated scanner failed: {case.name}")
        records.append({
            "name": case.name, "kind": "generated-scanner", "passed": True,
            "generator_status": left["status"],
            "generated_files": sorted(left["manifest"]),  # type: ignore[arg-type]
            "runtime_status": runtime["status"],
            "runtime_stdout_sha256": digest_bytes(runtime["stdout"]),  # type: ignore[arg-type]
        })

    evidence = {
        "schema": 1,
        "cases": len(records),
        "passed": sum(record["passed"] is True for record in records),
        "generated_scanners": len(CASES),
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: evidence[key] for key in ("cases", "passed", "generated_scanners")},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
