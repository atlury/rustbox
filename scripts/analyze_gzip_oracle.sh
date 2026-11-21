#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-gzip:2026-11-21 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    source=/rustbox-gzip/source
    volume=/rustbox-gzip
    output=/work/work/analysis/gzip-1.14/analyzers
    gcc_build=$volume/analyzer-gcc
    database_dir=$volume/production-compdb
    database=$database_dir/compile_commands.json
    rm -rf "$output" "$gcc_build" "$database_dir"
    mkdir -p "$output" "$gcc_build" "$database_dir"

    python3 - /work/work/analysis/gzip-1.14/oracle/clang-compile-commands.json \
      "$database" "$database_dir/sources.list" <<"PY"
import json,sys
from pathlib import Path
source_db,output_db,output_list=map(Path,sys.argv[1:])
records=json.loads(source_db.read_text())
sources=sorted({Path(record["file"]).resolve() for record in records})
roots=(Path("/rustbox-gzip/source"),Path("/rustbox-gzip/oracle-clang"))
if len(records) != 69 or len(sources) != 69:
    raise SystemExit("GNU Gzip production closure changed")
if any(not any(source.is_relative_to(root) for root in roots) for source in sources):
    raise SystemExit("GNU Gzip production closure escapes authenticated source/build")
output_db.write_text(json.dumps(records,indent=2)+"\n")
output_list.write_text("".join(f"{source}\n" for source in sources))
PY
    cp "$database" "$output/compile_commands.json"
    cp "$database_dir/sources.list" "$output/sources.list"

    cppcheck --enable=warning,style,performance,portability \
      --inline-suppr --suppress=missingIncludeSystem \
      --template="{file}:{line}:{column}: {severity}: {id}: {message}" \
      --project="$database" >"$output/cppcheck.log" 2>&1

    cd "$gcc_build"
    CC=gcc CFLAGS="-O0 -g -fno-omit-frame-pointer" \
      "$source/configure" --disable-dependency-tracking \
      >"$output/gcc-analyzer-setup.log" 2>&1
    make -j"$(nproc)" \
      CFLAGS="-O0 -g -fanalyzer -Wall -Wextra -fno-omit-frame-pointer" \
      >"$output/gcc-analyzer.log" 2>&1

    run-clang-tidy-18 -p "$database_dir" \
      -checks="clang-analyzer-*,bugprone-*,performance-*,portability-*" \
      -header-filter="^/rustbox-gzip/(source|oracle-clang)/" \
      >"$output/clang-analyzer-tidy.log" 2>&1

    xargs flawfinder --minlevel=1 --quiet <"$database_dir/sources.list" \
      >"$output/flawfinder.log" 2>&1

    if xargs -n1 sparse \
        -DHAVE_CONFIG_H -I"$volume/oracle-clang" \
        -I"$volume/oracle-clang/lib" -I"$source/lib" -I"$source" \
        -I/work/tools/sparse-compat \
        <"$database_dir/sources.list" >"$output/sparse.log" 2>&1
    then
      sparse_status=0
    else
      sparse_status=$?
    fi
    printf "%s\n" "$sparse_status" >"$output/sparse.status"
  '
