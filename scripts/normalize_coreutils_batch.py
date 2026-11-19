#!/usr/bin/env python3
"""Stage, semantic-patch, replay, and ABI-check a Coreutils batch."""

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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


def relative_source(path: Path, source_root: Path) -> Path:
    try:
        return path.resolve().relative_to(source_root.resolve())
    except ValueError as error:
        raise RuntimeError(f"compile input is outside canonical source: {path}") from error


def replay(arguments: list[str], output: Path, cwd: Path) -> dict[str, object]:
    command = list(arguments)
    output_index = command.index("-o") + 1
    command[output_index] = str(output)
    process = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    result: dict[str, object] = {
        "compiler": os.path.basename(command[0]),
        "exit_status": process.returncode,
        "stdout_sha256": hashlib.sha256(process.stdout.encode()).hexdigest(),
        "stderr_sha256": hashlib.sha256(process.stderr.encode()).hexdigest(),
    }
    if process.returncode:
        result["stderr"] = process.stderr[-4000:]
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--gcc-database", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    source_root = args.source_root.resolve()
    database = json.loads(args.database.read_text(encoding="utf-8"))
    gcc_database = json.loads(args.gcc_database.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    normalizations = manifest.get("c_normalization", [])
    if not normalizations:
        raise RuntimeError("batch declares no C normalization")
    if len(database) != manifest["expected_compile_commands"]:
        raise RuntimeError("compile database count differs from batch declaration")
    gcc_by_output: dict[str, dict[str, object]] = {}
    for entry in gcc_database:
        name = Path(entry["output"]).name
        if name in gcc_by_output:
            raise RuntimeError(f"GCC database has duplicate output basename: {name}")
        gcc_by_output[name] = entry

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    try:
        staged_source = staged / "source"
        staged_objects = staged / "objects/clang"
        staged_gcc = staged / "objects/gcc"
        staged_source.mkdir(parents=True)
        staged_objects.mkdir(parents=True)
        staged_gcc.mkdir(parents=True)

        rewritten = []
        source_records: dict[str, dict[str, object]] = {}
        for entry in database:
            source = Path(entry["file"])
            relative = relative_source(source, source_root)
            destination = staged_source / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            destination.chmod(destination.stat().st_mode | 0o200)
            if str(relative) in source_records:
                raise RuntimeError(f"batch contains multiple configurations for {relative}")
            source_records[str(relative)] = {
                "canonical_sha256": sha256(source),
                "staged_before_sha256": sha256(destination),
            }

            item = json.loads(json.dumps(entry))
            item["file"] = str(destination)
            item["arguments"] = [
                str(destination) if argument == str(source) else argument
                for argument in item["arguments"]
            ]
            macro_map = f"-fmacro-prefix-map={staged_source}={source_root}"
            compile_index = item["arguments"].index("-c")
            item["arguments"].insert(compile_index, macro_map)
            object_path = staged_objects / Path(item["output"]).name
            output_index = item["arguments"].index("-o") + 1
            item["arguments"][output_index] = str(object_path)
            item["output"] = str(object_path)
            rewritten.append(item)

        patch_records = []
        for declaration in normalizations:
            relative = Path(declaration["source"])
            source = staged_source / relative
            before = source.read_text(encoding="utf-8")
            expected_before_count = declaration.get("expected_before_count", 1)
            expected_after_count = declaration.get("expected_after_count", 1)
            actual_before_count = before.count(declaration["expected_before"])
            if actual_before_count != expected_before_count:
                raise RuntimeError(
                    f"normalization precondition count for {relative}: "
                    f"expected {expected_before_count}, found {actual_before_count}; "
                    f"needle={declaration['expected_before']!r}"
                )
            engine = declaration.get("engine", "coccinelle")
            if engine == "exact":
                replacement = declaration["replacement"]
                source.write_text(
                    before.replace(declaration["expected_before"], replacement),
                    encoding="utf-8",
                )
            elif engine == "coccinelle":
                patch = repository / declaration["semantic_patch"]
                if not patch.is_file():
                    raise RuntimeError(f"semantic patch does not exist: {patch}")
                with tempfile.TemporaryDirectory(prefix="rustbox-cocci-") as patch_temporary:
                    transformed = Path(patch_temporary) / source.name
                    patch_process = subprocess.run(
                        ["spatch", "--sp-file", str(patch), str(source), "-o", str(transformed)],
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    if patch_process.returncode:
                        raise RuntimeError(
                            f"semantic patch failed: {relative}: {patch_process.stderr.strip()}"
                        )
                    if not transformed.is_file():
                        raise RuntimeError(f"semantic patch produced no output: {relative}")
                    shutil.copy2(transformed, source)
            else:
                raise RuntimeError(f"unknown normalization engine: {engine}")
            after = source.read_text(encoding="utf-8")
            if (
                declaration["expected_before"] in after
                or after.count(declaration["expected_after"]) != expected_after_count
            ):
                candidates = [
                    line.strip() for line in after.splitlines()
                    if "sync_arg" in line and "ok" in line
                ]
                raise RuntimeError(
                    f"semantic patch postcondition failed: {relative}; candidates={candidates!r}"
                )
            patch_records.append({
                **declaration,
                "verified_before_count": expected_before_count,
                "verified_after_count": expected_after_count,
                "engine": engine,
                "before_sha256": hashlib.sha256(before.encode()).hexdigest(),
                "after_sha256": hashlib.sha256(after.encode()).hexdigest(),
            })

        database_path = staged / "compile_commands.json"
        database_path.write_text(json.dumps(rewritten, indent=2) + "\n", encoding="utf-8")

        replay_results = []
        abi_results = []
        changed_sources = {item["source"] for item in normalizations}
        for entry in rewritten:
            source_relative = str(relative_source(Path(entry["file"]), staged_source))
            clang_output = Path(entry["output"])
            gcc_output = staged_gcc / clang_output.name
            gcc_entry = gcc_by_output.get(clang_output.name)
            if gcc_entry is None:
                raise RuntimeError(f"GCC database lacks {clang_output.name}")
            gcc_source = Path(gcc_entry["file"])
            if relative_source(gcc_source, source_root) != Path(source_relative):
                raise RuntimeError(f"Clang/GCC source mismatch for {clang_output.name}")
            gcc_arguments = [
                str(staged_source / source_relative) if argument == str(gcc_source) else argument
                for argument in gcc_entry["arguments"]
            ]
            gcc_compile_index = gcc_arguments.index("-c")
            gcc_arguments.insert(
                gcc_compile_index,
                f"-fmacro-prefix-map={staged_source}={source_root}",
            )
            clang_result = replay(entry["arguments"], clang_output, Path(entry["directory"]))
            gcc_result = replay(gcc_arguments, gcc_output, Path(gcc_entry["directory"]))
            replay_results.append({
                "source": source_relative,
                "clang": clang_result,
                "gcc": gcc_result,
            })
            if clang_result["exit_status"] or gcc_result["exit_status"]:
                raise RuntimeError(
                    f"compiler replay failed: {source_relative}: "
                    f"clang={clang_result!r}; gcc={gcc_result!r}"
                )
            if source_relative in changed_sources:
                canonical_object = Path(database[[x["file"] for x in database].index(
                    str(source_root / source_relative)
                )]["output"])
                abi = subprocess.run(
                    ["abidiff", str(canonical_object), str(clang_output)],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                canonical_symbols = subprocess.run(
                    ["nm", "-g", "--defined-only", str(canonical_object)],
                    check=True, text=True, stdout=subprocess.PIPE,
                ).stdout
                normalized_symbols = subprocess.run(
                    ["nm", "-g", "--defined-only", str(clang_output)],
                    check=True, text=True, stdout=subprocess.PIPE,
                ).stdout
                def symbol_signature(text: str) -> list[tuple[str, str]]:
                    return sorted(
                        (parts[-2], parts[-1])
                        for line in text.splitlines()
                        if len(parts := line.split()) >= 2
                    )

                if abi.returncode != 0 or symbol_signature(canonical_symbols) != symbol_signature(normalized_symbols):
                    raise RuntimeError(f"ABI or exported symbols changed: {source_relative}")
                abi_results.append({
                    "source": source_relative,
                    "abidiff_exit_status": abi.returncode,
                    "exported_symbols_identical": True,
                    "abidiff_stdout_sha256": hashlib.sha256(abi.stdout.encode()).hexdigest(),
                })

        for relative, record in source_records.items():
            staged_path = staged_source / relative
            record["normalized_sha256"] = sha256(staged_path)
            record["changed"] = record["canonical_sha256"] != record["normalized_sha256"]
            if record["changed"] != (relative in changed_sources):
                raise RuntimeError(f"unexpected normalization change set: {relative}")

        published = json.loads(
            json.dumps(rewritten).replace(str(staged), str(output))
        )
        database_path.write_text(json.dumps(published, indent=2) + "\n", encoding="utf-8")

        evidence = {
            "schema": 1,
            "batch": manifest["name"],
            "input_database_sha256": sha256(args.database),
            "gcc_database_sha256": sha256(args.gcc_database),
            "normalized_database_sha256": sha256(database_path),
            "sources": dict(sorted(source_records.items())),
            "semantic_patches": patch_records,
            "compiler_replays": replay_results,
            "abi_checks": abi_results,
        }
        (staged / "normalization.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if output.exists():
            shutil.rmtree(output)
        staged.rename(output)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    print(json.dumps({
        "batch": evidence["batch"],
        "changed_sources": len(changed_sources),
        "compile_commands": len(rewritten),
        "abi_checks": len(abi_results),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
