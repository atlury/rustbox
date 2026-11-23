#!/usr/bin/env python3
"""Create curl's exact 240-source multicall C2Rust database."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


SOURCE_ROOT = Path("/rustbox-curl/normalized-source")
BUILD_ROOT = Path("/rustbox-curl/normalized-clang")


def source_name(path: Path) -> str:
    if path.is_relative_to(SOURCE_ROOT):
        return path.relative_to(SOURCE_ROOT).as_posix()
    if path in {
        BUILD_ROOT / "src/tool_ca_embed.c",
        BUILD_ROOT / "src/tool_hugehelp.c",
    }:
        return "generated/" + path.relative_to(BUILD_ROOT).as_posix()
    raise RuntimeError(f"curl source escapes normalized production closure: {path}")


def replace_root(value: str, destination: Path) -> str:
    for root in (SOURCE_ROOT, BUILD_ROOT):
        prefix = str(root)
        if value == prefix:
            return str(destination)
        if value.startswith(prefix + "/"):
            return str(destination) + value[len(prefix):]
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--normalization", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-output", type=Path, required=True)
    parser.add_argument("--only", action="append", default=[])
    args = parser.parse_args()

    records = json.loads(args.database.read_text())
    normalization = json.loads(args.normalization.read_text())
    oracle = json.loads(args.oracle.read_text())
    expected = set(oracle["scope"]["production_sources"])
    if normalization["changed_sources"] != ["src/tool_main.c"]:
        raise RuntimeError("curl normalization source set changed")
    if normalization["entrypoint"] != "rustbox_curl_main":
        raise RuntimeError("curl multicall entrypoint changed")
    if len(records) != 477 or len(expected) != 240:
        raise RuntimeError("curl normalized database or production closure changed")

    selected: dict[str, dict[str, object]] = {}
    unit_test_actions = 0
    for original in records:
        arguments = [str(value) for value in original["arguments"]]
        if "-DUNITTESTS" in arguments:
            unit_test_actions += 1
            continue
        relative = source_name(Path(str(original["file"])).resolve())
        if relative not in expected:
            raise RuntimeError(f"unexpected curl production source: {relative}")
        if relative in selected:
            raise RuntimeError(f"duplicate curl production compile action: {relative}")
        selected[relative] = original
    if unit_test_actions != 237 or set(selected) != expected:
        raise RuntimeError(
            f"curl C2Rust closure changed: unit={unit_test_actions}, "
            f"delta={sorted(set(selected) ^ expected)}"
        )

    if args.source_output.exists():
        shutil.rmtree(args.source_output)
    shutil.copytree(
        SOURCE_ROOT,
        args.source_output,
        symlinks=True,
        ignore=shutil.ignore_patterns(
            ".deps", ".libs", "*.o", "*.a", "testsuite.log", "test-suite.log",
        ),
    )
    shutil.copy2(BUILD_ROOT / "lib/curl_config.h", args.source_output / "lib")
    for name in ("tool_ca_embed.c", "tool_hugehelp.c"):
        shutil.copy2(BUILD_ROOT / "src" / name, args.source_output / "src" / name)
    config = args.source_output / "lib/curl_config.h"
    config_text = config.read_text()
    atomic = "#define HAVE_ATOMIC 1"
    if config_text.count(atomic) != 1:
        raise RuntimeError("curl atomic-lock configuration changed")
    config.write_text(config_text.replace(atomic, "/* #undef HAVE_ATOMIC */"))
    portable_swab = args.source_output / "portable-include/asm/swab.h"
    portable_swab.parent.mkdir(parents=True)
    portable_swab.write_text(
        "/* C2Rust: select linux/swab.h's equivalent portable C fallback. */\n"
        "#ifndef _ASM_X86_SWAB_H\n"
        "#define _ASM_X86_SWAB_H\n"
        "#endif\n"
    )

    requested = set(args.only)
    if requested and not requested <= expected:
        raise RuntimeError(f"unknown curl diagnostic source: {sorted(requested - expected)}")
    names = sorted(requested or expected)
    output_records: list[dict[str, object]] = []
    for relative in names:
        record = json.loads(json.dumps(selected[relative]))
        arguments = [str(value) for value in record["arguments"]]
        if arguments.count("-c") != 1:
            raise RuntimeError(f"malformed curl compile action: {relative}")
        arguments[1:1] = [f"-I{args.source_output}/portable-include"]
        arguments[arguments.index("-c"):arguments.index("-c")] = [
            "-DRUSTBOX_MULTICALL=1",
            "-DCURL_DISABLE_TYPECHECK=1",
        ]
        record["arguments"] = [
            replace_root(value, args.source_output) for value in arguments
        ]
        record["directory"] = replace_root(str(record["directory"]), args.source_output)
        record["file"] = replace_root(str(record["file"]), args.source_output)
        record["output"] = replace_root(str(record["output"]), args.source_output)
        output_records.append(record)

    if len(output_records) != len(names):
        raise RuntimeError("curl output action count changed")
    if not all("-DRUSTBOX_MULTICALL=1" in record["arguments"]
               for record in output_records):
        raise RuntimeError("curl multicall define missing")
    if not all("-DCURL_DISABLE_TYPECHECK=1" in record["arguments"]
               for record in output_records):
        raise RuntimeError("curl translation typecheck configuration missing")
    if any("-DUNITTESTS" in record["arguments"] for record in output_records):
        raise RuntimeError("curl unit-test variant escaped into production translation")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_records, indent=2) + "\n")
    print(json.dumps({
        "commands": len(output_records),
        "excluded_unit_test_actions": unit_test_actions,
        "multicall_define": True,
        "portable_atomic_lock": "pthread mutex fallback",
        "portable_linux_swab": True,
        "production_sources": len(expected),
        "selected_diagnostic_sources": args.only,
        "translation_typecheck_macro_disabled": True,
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
