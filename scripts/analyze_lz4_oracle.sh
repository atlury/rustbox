#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-lz4:2026-11-21 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    release=/work/work/upstream/lz4-1.11.1
    source=/rustbox-lz4/analyzer-source
    output=/work/work/analysis/lz4-1.11.1/analyzers
    database=/work/work/analysis/lz4-1.11.1/oracle/clang-compile-commands.json
    rm -rf "$source" "$output"
    cp -a "$release" "$source"
    mkdir -p "$output"

    python3 - "$database" "$output/sources.list" <<"PY"
import json,sys
from pathlib import Path
database,output=map(Path,sys.argv[1:])
records=json.loads(database.read_text())
sources=sorted({Path(record["file"]).resolve() for record in records})
root=Path("/rustbox-lz4/source-clang")
if len(records) != 24 or len(sources) != 12:
    raise SystemExit("LZ4 production closure changed")
if any(not source.is_relative_to(root) for source in sources):
    raise SystemExit("LZ4 production closure escapes canonical source")
output.write_text("".join(f"{source}\n" for source in sources))
PY
    cp "$database" "$output/compile_commands.json"

    cppcheck --enable=warning,style,performance,portability \
      --inline-suppr --suppress=missingIncludeSystem \
      --template="{file}:{line}:{column}: {severity}: {id}: {message}" \
      --project="$database" >"$output/cppcheck.log" 2>&1

    make -C "$source/programs" clean >/dev/null
    make -j"$(nproc)" -C "$source/programs" all CC=gcc \
      CFLAGS="-O0 -g -fanalyzer -Wall -Wextra -fno-omit-frame-pointer" \
      >"$output/gcc-analyzer.log" 2>&1

    run-clang-tidy-18 -p "$output" \
      -checks="clang-analyzer-*,bugprone-*,performance-*,portability-*" \
      -header-filter="^/rustbox-lz4/source-clang/(lib|programs)/" \
      >"$output/clang-analyzer-tidy.log" 2>&1

    xargs flawfinder --minlevel=1 --quiet <"$output/sources.list" \
      >"$output/flawfinder.log" 2>&1

    if xargs -n1 sparse -I/rustbox-lz4/source-clang/lib \
        -DXXH_NAMESPACE=LZ4_ -DLZ4IO_MULTITHREAD -DLZ4F_MULTITHREAD=1 \
        -I/work/tools/sparse-compat \
        <"$output/sources.list" >"$output/sparse.log" 2>&1
    then
      sparse_status=0
    else
      sparse_status=$?
    fi
    printf "%s\n" "$sparse_status" >"$output/sparse.status"
  '
