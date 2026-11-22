#!/usr/bin/env python3
"""0BSD. Verify Flex's flex++ and lex compatibility frontends byte-for-byte."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
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
CXX_SPEC = br"""%option noyywrap nodefault
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


def invoke(command: list[bytes], cwd: bytes, data: bytes | None = None) -> dict[str, object]:
    result = subprocess.run(
        command, cwd=cwd, input=data, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
    )
    return {"status": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def files(directory: bytes) -> dict[bytes, bytes]:
    result = {}
    with os.scandir(directory) as entries:
        for entry in entries:
            name = os.fsencode(entry.name)
            if entry.is_file() and not name.endswith(b".l") and name != b"scanner":
                result[name] = Path(os.fsdecode(os.path.join(directory, name))).read_bytes()
    return result


def generation(binary: Path, invocation: bytes, arguments: list[bytes], source: bytes,
               source_root: Path, cxx: bool, raw_name: bool = False) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="rustbox-flex-frontend-") as text_directory:
        directory = os.fsencode(text_directory)
        link = os.path.join(directory, invocation)
        os.symlink(os.fsencode(binary), link)
        source_name = b"scanner-\xff.l" if raw_name else b"scanner.l"
        source_path = os.path.join(directory, source_name)
        descriptor = os.open(source_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(descriptor, source)
        finally:
            os.close(descriptor)
        result = invoke([b"./" + invocation, *arguments, source_name], directory)
        manifest = files(directory)
        manifest.pop(invocation, None)
        runtime = None
        if result["status"] == 0 and not raw_name:
            suffix = b".cc" if cxx else b".c"
            generated = [name for name in manifest if name.endswith(suffix)]
            if len(generated) != 1:
                raise RuntimeError(f"{invocation!r}: generated sources {sorted(manifest)!r}")
            compiler = b"g++" if cxx else b"gcc"
            compiled = invoke([
                compiler, b"-O2", b"-I", os.fsencode(source_root / "src"),
                generated[0], b"-o", b"scanner",
            ], directory)
            if compiled["status"] != 0:
                raise RuntimeError(compiled["stderr"].decode(errors="replace"))
            runtime = invoke([b"./scanner"], directory, INPUT)
        return {**result, "manifest": manifest, "runtime": runtime}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def comparable(record: dict[str, object]) -> dict[str, object]:
    return {key: record[key] for key in ("status", "stdout", "stderr", "manifest", "runtime")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--hybrid", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    cases = (
        ("flex++", b"flex++", [], CXX_SPEC, True, False),
        ("lex", b"lex", [], C_SPEC, False, False),
        ("lex-raw-filename", b"lex", [], C_SPEC, False, True),
    )
    records = []
    for name, invocation, hybrid_arguments, source, cxx, raw_name in cases:
        canonical_invocation = b"flex++" if invocation == b"flex++" else b"flex"
        canonical_arguments = [] if invocation == b"flex++" else [b"-l"]
        expected = generation(
            args.canonical, canonical_invocation, canonical_arguments,
            source, args.source, cxx, raw_name,
        )
        actual = generation(
            args.hybrid, invocation, hybrid_arguments,
            source, args.source, cxx, raw_name,
        )
        if comparable(expected) != comparable(actual):
            raise RuntimeError(f"Flex compatibility frontend mismatch: {name}")
        runtime = expected["runtime"]
        if runtime is not None and runtime["status"] != 0:  # type: ignore[index]
            raise RuntimeError(f"Flex compatibility scanner failed: {name}")
        records.append({
            "name": name,
            "passed": True,
            "status": expected["status"],
            "stdout_sha256": digest(expected["stdout"]),  # type: ignore[arg-type]
            "stderr_sha256": digest(expected["stderr"]),  # type: ignore[arg-type]
            "generated_files": sorted(os.fsdecode(item) for item in expected["manifest"]),  # type: ignore[arg-type]
            "runtime_status": None if runtime is None else runtime["status"],  # type: ignore[index]
        })

    evidence = {"schema": 1, "cases": len(records), "passed": len(records), "records": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"cases": len(records), "passed": len(records)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
