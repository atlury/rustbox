#!/usr/bin/env python3
"""Create XZ's exact portable multicall C2Rust database.

XZ compiles a few common helpers once per executable and compiles xzdec.c
twice, with and without LZMADEC.  C2Rust needs one record for each common
source but distinct source names for the two decoder personalities.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


SOURCE_ROOT = Path("/rustbox-xz/normalized-clang")


def replace_root(value: str, destination: Path) -> str:
    prefix = str(SOURCE_ROOT)
    if value == prefix:
        return str(destination)
    if value.startswith(prefix + "/"):
        return str(destination) + value[len(prefix) :]
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-output", type=Path, required=True)
    args = parser.parse_args()

    records = json.loads(args.database.read_text())
    oracle = json.loads(args.oracle.read_text())
    expected = set(oracle["inventory"]["production_sources"])
    if len(records) != 113 or len(expected) != 101:
        raise RuntimeError("XZ production database or oracle closure changed")

    grouped: dict[str, list[dict[str, object]]] = {}
    for original in records:
        source = Path(str(original["file"])).resolve()
        if not source.is_relative_to(SOURCE_ROOT):
            raise RuntimeError(f"XZ source escapes normalized closure: {source}")
        relative = source.relative_to(SOURCE_ROOT).as_posix()
        if relative not in expected:
            raise RuntimeError(f"unexpected XZ production source: {relative}")
        grouped.setdefault(relative, []).append(original)
    if set(grouped) != expected:
        raise RuntimeError(f"XZ C2Rust closure changed: {sorted(set(grouped) ^ expected)}")

    if args.source_output.exists():
        shutil.rmtree(args.source_output)
    # Libtool leaves a generated .libs/liblzma.la symlink in the build tree.
    # It is neither a source nor a preprocessor input, and Docker Desktop cannot
    # reproduce it reliably on the host bind mount.
    shutil.copytree(
        SOURCE_ROOT,
        args.source_output,
        symlinks=True,
        ignore=shutil.ignore_patterns(".libs"),
    )
    config = args.source_output / "config.h"
    config_text = config.read_text()
    intrinsic_define = "#define HAVE_IMMINTRIN_H 1"
    if config_text.count(intrinsic_define) != 1:
        raise RuntimeError("XZ immintrin configuration changed")
    config.write_text(
        config_text.replace(
            intrinsic_define,
            "/* #undef HAVE_IMMINTRIN_H -- portable C2Rust configuration */",
        )
        + "\n/* C2Rust cannot represent XZ's optional x86-64 inline assembly. */\n"
        + "#define LZMA_RANGE_DECODER_CONFIG 0\n"
    )
    arm64 = args.source_output / "src/liblzma/simple/arm64.c"
    arm64_text = arm64.read_text()
    loop_pragma = "#\tpragma clang loop vectorize(disable)"
    if arm64_text.count(loop_pragma) != 1:
        raise RuntimeError("XZ ARM64 loop pragma changed")
    arm64.write_text(
        arm64_text.replace(
            loop_pragma,
            "/* C2Rust portability: omit the optional Clang vectorization hint. */",
        )
    )

    selected: list[tuple[str, dict[str, object]]] = []
    lzmadec_record: dict[str, object] | None = None
    for relative in sorted(grouped):
        candidates = grouped[relative]
        if relative == "src/xzdec/xzdec.c":
            plain = [r for r in candidates if "-DLZMADEC" not in r["arguments"]]
            lzma = [r for r in candidates if "-DLZMADEC" in r["arguments"]]
            if len(plain) != 1 or len(lzma) != 1:
                raise RuntimeError("XZ decoder personalities changed")
            chosen = plain[0]
            lzmadec_record = lzma[0]
        elif len(candidates) == 1:
            chosen = candidates[0]
        else:
            xz_actions = [
                r
                for r in candidates
                if Path(str(r["output"])).parent.name == "xz"
            ]
            if len(xz_actions) != 1:
                raise RuntimeError(f"no unique XZ frontend action for {relative}")
            chosen = xz_actions[0]
        selected.append((relative, chosen))

    if lzmadec_record is None:
        raise RuntimeError("missing LZMA decoder personality")

    output_records: list[dict[str, object]] = []
    for relative, original in selected:
        record = json.loads(json.dumps(original))
        arguments = list(record["arguments"])
        if arguments.count("-c") != 1:
            raise RuntimeError(f"malformed XZ compile action for {relative}")
        arguments.insert(arguments.index("-c"), "-DRUSTBOX_MULTICALL=1")
        record["arguments"] = [replace_root(a, args.source_output) for a in arguments]
        record["directory"] = replace_root(str(record["directory"]), args.source_output)
        record["file"] = replace_root(str(record["file"]), args.source_output)
        record["output"] = replace_root(str(record["output"]), args.source_output)
        output_records.append(record)

    personality_relative = "src/xzdec/rustbox_lzmadec_personality.c"
    personality_source = args.source_output / personality_relative
    shutil.copyfile(args.source_output / "src/xzdec/xzdec.c", personality_source)
    personality = json.loads(json.dumps(lzmadec_record))
    arguments = list(personality["arguments"])
    if arguments.count("-c") != 1 or arguments.count("xzdec.c") != 1:
        raise RuntimeError("malformed LZMA decoder compile action")
    arguments[arguments.index("xzdec.c")] = personality_source.name
    arguments[arguments.index("-c"):arguments.index("-c")] = ["-DRUSTBOX_MULTICALL=1"]
    personality["arguments"] = [replace_root(a, args.source_output) for a in arguments]
    personality["directory"] = replace_root(
        str(personality["directory"]), args.source_output
    )
    personality["file"] = str(personality_source)
    personality["output"] = str(personality_source.with_suffix(".o"))
    output_records.append(personality)

    if len(output_records) != 102:
        raise RuntimeError(f"expected 102 XZ translation actions, got {len(output_records)}")
    if not all("-DRUSTBOX_MULTICALL=1" in r["arguments"] for r in output_records):
        raise RuntimeError("XZ multicall define missing")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_records, indent=2) + "\n")
    print(
        json.dumps(
            {
                "commands": len(output_records),
                "production_sources": len(selected),
                "decoder_personalities": 2,
                "multicall_define": True,
                "portable_crc": True,
                "portable_memcmp_and_copy": True,
                "portable_range_decoder": True,
                "removed_optimization_pragmas": 1,
                "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
