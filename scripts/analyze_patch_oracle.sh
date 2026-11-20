#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-patch:2026-11-20 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    readonly source=/rustbox-patch/source
    readonly volume=/rustbox-patch
    readonly output=/work/work/analysis/patch-2.8/analyzers
    readonly gcc_build=$volume/analyzer-gcc
    readonly database_dir=$volume/production-compdb
    readonly database=$database_dir/compile_commands.json
    rm -rf "$output" "$gcc_build" "$database_dir"
    mkdir -p "$output" "$gcc_build" "$database_dir"

    cp /work/work/analysis/patch-2.8/oracle/clang-compile-commands.json "$database"
    python3 - "$database" "$database_dir/sources.list" <<"PY"
import json,sys
from pathlib import Path
database=Path(sys.argv[1]); output=Path(sys.argv[2])
records=json.loads(database.read_text())
sources=sorted({Path(record["file"]).resolve() for record in records})
root=Path("/rustbox-patch/source")
if len(records) != 67 or len(sources) != 67:
    raise SystemExit("GNU patch production closure changed")
if any(not source.is_relative_to(root) for source in sources):
    raise SystemExit("GNU patch production closure escapes signed source")
output.write_text("".join(f"{source}\n" for source in sources))
PY
    cp "$database" "$output/compile_commands.json"
    cp "$database_dir/sources.list" "$output/sources.list"

    cppcheck --enable=warning,style,performance,portability \
      --inline-suppr --suppress=missingIncludeSystem \
      --template="{file}:{line}:{column}: {severity}: {id}: {message}" \
      --project="$database" >"$output/cppcheck.log" 2>&1

    cd "$gcc_build"
    CC=gcc CFLAGS="-O0 -g -fanalyzer -Wall -Wextra -fno-omit-frame-pointer" \
      "$source/configure" --disable-dependency-tracking \
      >"$output/gcc-analyzer-setup.log" 2>&1
    make -j"$(nproc)" >"$output/gcc-analyzer.log" 2>&1

    run-clang-tidy-18 -p "$database_dir" \
      -checks="clang-analyzer-*,bugprone-*,performance-*,portability-*" \
      -header-filter="^/rustbox-patch/source/(src|lib)/" \
      >"$output/clang-analyzer-tidy.log" 2>&1

    xargs flawfinder --minlevel=1 --quiet < "$database_dir/sources.list" \
      >"$output/flawfinder.log" 2>&1

    if xargs -n1 sparse \
        -DHAVE_CONFIG_H -I"$volume/oracle-clang" \
        -I"$volume/oracle-clang/lib" -I"$source/lib" -I"$source/src" \
        -I/work/tools/sparse-compat \
        < "$database_dir/sources.list" >"$output/sparse.log" 2>&1
    then
      sparse_status=0
    else
      sparse_status=$?
    fi
    printf "%s\n" "$sparse_status" > "$output/sparse.status"
  '
