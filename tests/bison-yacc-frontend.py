#!/usr/bin/env python3
"""0BSD. Compare canonical and native Rustbox yacc personalities."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


GRAMMAR = br"""%{
#include <stdio.h>
int yylex (void);
void yyerror (const char *message);
%}
%%
start: %empty;
%%
int yylex (void) { return 0; }
void yyerror (const char *message) { fprintf (stderr, "%s\n", message); }
int main (void) { return yyparse (); }
"""


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def exercise(binary: Path, datadir: Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="rustbox-yacc-") as raw:
        directory = Path(raw)
        (directory / "grammar.y").write_bytes(GRAMMAR)
        environment = dict(os.environ)
        environment["BISON_PKGDATADIR"] = str(datadir)
        result = subprocess.run(
            [str(binary), "-d", "grammar.y"], cwd=directory, env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        generated = {
            path.name: path.read_bytes()
            for path in sorted(directory.iterdir())
            if path.name != "grammar.y"
        }
        compile_result = subprocess.run(
            ["cc", "-std=gnu11", "y.tab.c", "-o", "parser"], cwd=directory,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        ) if result.returncode == 0 else None
        runtime = subprocess.run(
            ["./parser"], cwd=directory, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False,
        ) if compile_result is not None and compile_result.returncode == 0 else None
        return {
            "status": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "generated": generated,
            "compile_status": None if compile_result is None else compile_result.returncode,
            "compile_stdout": b"" if compile_result is None else compile_result.stdout,
            "compile_stderr": b"" if compile_result is None else compile_result.stderr,
            "runtime_status": None if runtime is None else runtime.returncode,
            "runtime_stdout": b"" if runtime is None else runtime.stdout,
            "runtime_stderr": b"" if runtime is None else runtime.stderr,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", required=True, type=Path)
    parser.add_argument("--canonical-datadir", required=True, type=Path)
    parser.add_argument("--hybrid", required=True, type=Path)
    parser.add_argument("--hybrid-datadir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    canonical = exercise(args.canonical, args.canonical_datadir)
    hybrid = exercise(args.hybrid, args.hybrid_datadir)
    if canonical != hybrid:
        raise RuntimeError("native yacc personality differs from GNU yacc")
    if canonical["status"] != 0 or canonical["compile_status"] != 0 or canonical["runtime_status"] != 0:
        raise RuntimeError("canonical yacc exercise did not complete")
    generated = canonical["generated"]
    evidence = {
        "schema": 1,
        "passed": True,
        "status": canonical["status"],
        "compile_status": canonical["compile_status"],
        "runtime_status": canonical["runtime_status"],
        "stdout_sha256": sha256(canonical["stdout"]),
        "stderr_sha256": sha256(canonical["stderr"]),
        "generated_sha256": {
            name: sha256(contents) for name, contents in sorted(generated.items())
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"generated_files": len(generated), "passed": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
