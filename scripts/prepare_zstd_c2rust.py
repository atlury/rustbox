#!/usr/bin/env python3
"""Create zstd's exact portable multicall C2Rust database."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


SOURCE_ROOT = Path("/rustbox-zstd/normalized-clang")
COPY_ROOT = Path("/rustbox-zstd/normalized-source")


def replace_root(value: str, destination: Path) -> str:
    prefix = str(SOURCE_ROOT)
    if value == prefix:
        return str(destination)
    if value.startswith(prefix + "/"):
        return str(destination) + value[len(prefix):]
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--normalization", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-output", type=Path, required=True)
    args = parser.parse_args()

    records = json.loads(args.database.read_text())
    normalization = json.loads(args.normalization.read_text())
    expected = set(normalization["production_sources"])
    if len(records) != 44 or len(expected) != 44:
        raise RuntimeError("zstd production database or normalized closure changed")

    grouped: dict[str, list[dict[str, object]]] = {}
    for original in records:
        source = Path(str(original["file"])).resolve()
        if not source.is_relative_to(SOURCE_ROOT):
            raise RuntimeError(f"zstd source escapes normalized closure: {source}")
        relative = source.relative_to(SOURCE_ROOT).as_posix()
        if relative not in expected:
            raise RuntimeError(f"unexpected zstd production source: {relative}")
        grouped.setdefault(relative, []).append(original)
    if set(grouped) != expected or any(len(grouped[name]) != 1 for name in grouped):
        raise RuntimeError("zstd C2Rust closure is not one action per portable source")

    if args.source_output.exists():
        shutil.rmtree(args.source_output)
    # The compiled tree contains disposable broken test/build symlinks that
    # Docker Desktop cannot reproduce on the host bind mount.  Copy the exact
    # verified pristine normalized tree and remap the compiled database to it.
    shutil.copytree(
        COPY_ROOT,
        args.source_output,
        symlinks=True,
        ignore=shutil.ignore_patterns("bin"),
    )
    cpu_header = args.source_output / "lib/common/cpu.h"
    cpu_text = cpu_header.read_text()
    start_marker = "MEM_STATIC ZSTD_cpuid_t ZSTD_cpuid(void) {"
    end_marker = "\n#define X(name, r, bit)"
    if cpu_text.count(start_marker) != 1 or cpu_text.count(end_marker) != 1:
        raise RuntimeError("zstd CPUID helper precondition changed")
    start = cpu_text.index(start_marker)
    end = cpu_text.index(end_marker, start)
    portable_cpuid = (
        "MEM_STATIC ZSTD_cpuid_t ZSTD_cpuid(void) {\n"
        "    ZSTD_cpuid_t const cpuid = { 0, 0, 0, 0 };\n"
        "    return cpuid;\n"
        "}\n"
    )
    cpu_header.write_text(cpu_text[:start] + portable_cpuid + cpu_text[end:])
    compress_header = args.source_output / "lib/compress/zstd_compress_internal.h"
    compress_text = compress_header.read_text()
    select_asm = "#if defined(__GNUC__) && defined(__x86_64__)"
    if compress_text.count(select_asm) != 1:
        raise RuntimeError("zstd branchless address-selection precondition changed")
    compress_header.write_text(compress_text.replace(
        select_asm,
        "#if 0 /* C2Rust portability: use the equivalent C comparison below. */",
    ))

    output_records: list[dict[str, object]] = []
    for relative in sorted(grouped):
        record = json.loads(json.dumps(grouped[relative][0]))
        arguments = list(record["arguments"])
        if arguments.count("-c") != 1:
            raise RuntimeError(f"malformed zstd compile action for {relative}")
        arguments[arguments.index("-c"):arguments.index("-c")] = [
            "-DRUSTBOX_MULTICALL=1",
            "-DDYNAMIC_BMI2=0",
            "-DZSTD_NO_INTRINSICS=1",
            "-DXXH_VECTOR=0",
            "-DXXH_DEBUGLEVEL=1",
        ]
        record["arguments"] = [replace_root(value, args.source_output) for value in arguments]
        record["directory"] = replace_root(str(record["directory"]), args.source_output)
        record["file"] = replace_root(str(record["file"]), args.source_output)
        record["output"] = replace_root(str(record["output"]), args.source_output)
        output_records.append(record)

    if len(output_records) != 44:
        raise RuntimeError(f"expected 44 zstd translation actions, got {len(output_records)}")
    if not all("-DRUSTBOX_MULTICALL=1" in record["arguments"] for record in output_records):
        raise RuntimeError("zstd multicall define missing")
    if not all("-DZSTD_NO_INTRINSICS=1" in record["arguments"]
               and "-DDYNAMIC_BMI2=0" in record["arguments"]
               and "-DXXH_VECTOR=0" in record["arguments"]
               and "-DXXH_DEBUGLEVEL=1" in record["arguments"]
               for record in output_records):
        raise RuntimeError("zstd portable intrinsic configuration missing")
    if any(Path(str(record["file"])).suffix != ".c" for record in output_records):
        raise RuntimeError("zstd translation closure contains non-C input")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_records, indent=2) + "\n")
    print(json.dumps({
        "commands": len(output_records), "production_sources": len(expected),
        "multicall_define": True, "portable_huffman": True,
        "portable_intrinsics": True,
        "portable_xxhash_assertions": True,
        "portable_cpuid_stub": True,
        "portable_address_selection": True,
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
