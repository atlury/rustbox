#!/usr/bin/env python3
"""Replay a C compile database under GCC's interprocedural analyzer."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def analyzer_command(record: dict[str, object], compiler: str, output: Path) -> list[str]:
    original = [str(value) for value in record["arguments"]]
    command = [compiler]
    skip = False
    for argument in original[1:]:
        if skip:
            skip = False
            continue
        if argument == "-o":
            skip = True
            continue
        if argument == "-Qunused-arguments":
            continue
        command.append(argument)
    command.extend((
        "-fanalyzer", "-Wall", "-Wextra", "-fno-diagnostics-color",
        "-fno-omit-frame-pointer", "-o", str(output),
    ))
    return command


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--compiler", default="gcc")
    parser.add_argument("--jobs", type=int, default=max(1, os.cpu_count() or 1))
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()

    records = json.loads(args.database.read_text())
    if not isinstance(records, list) or not records:
        raise RuntimeError("compile database is empty")

    with tempfile.TemporaryDirectory(prefix="rustbox-gcc-analyzer-") as directory:
        objects = Path(directory)

        def run(item: tuple[int, dict[str, object]]) -> dict[str, object]:
            index, record = item
            source = str(record["file"])
            command = analyzer_command(record, args.compiler, objects / f"{index}.o")
            try:
                result = subprocess.run(
                    command,
                    cwd=str(record["directory"]),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=args.timeout,
                )
                return {
                    "index": index, "source": source, "status": result.returncode,
                    "timed_out": False, "output": result.stdout,
                }
            except subprocess.TimeoutExpired as error:
                output = error.stdout or ""
                if isinstance(output, bytes):
                    output = output.decode(errors="replace")
                return {
                    "index": index, "source": source, "status": 124,
                    "timed_out": True, "output": output,
                }

        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            results = list(executor.map(run, enumerate(records)))

    results.sort(key=lambda result: int(result["index"]))
    args.log.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open("w") as stream:
        for result in results:
            stream.write(
                f"### {result['index'] + 1}/{len(results)} {result['source']} "
                f"status={result['status']} timeout={str(result['timed_out']).lower()}\n"
            )
            stream.write(str(result["output"]))
            if result["output"] and not str(result["output"]).endswith("\n"):
                stream.write("\n")

    failures = [result for result in results if result["status"] != 0]
    summary = {
        "schema": 1,
        "compiler": args.compiler,
        "compile_actions": len(results),
        "passed": len(results) - len(failures),
        "failed": len(failures),
        "timed_out": sum(bool(result["timed_out"]) for result in results),
        "failures": [
            {key: result[key] for key in ("index", "source", "status", "timed_out")}
            for result in failures
        ],
    }
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
